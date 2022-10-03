import logging
import ujson as json
from collections import defaultdict
from database import ydb_client
from telegram.ext import (
    DictPersistence,
    Dispatcher
)
from telegram.ext.callbackdatacache import CallbackDataCache
from telegram.ext.conversationhandler import ConversationHandler
from telegram.ext.handler import Handler


class PersistentDispatcher(Dispatcher):
    """
    Modified dispatcher class that allows to load and save persistence data after initialization
    and to check whether all ConversationHandlers are used with the proper settings for using
    with YDBPersistence
    """

    def add_handler(
        self,
        handler: Handler,
        **kwargs
        ):
        """
        Add handler and check its compatibility with YDBPersistence
        """

        super().add_handler(handler, **kwargs)

        if isinstance(self.persistence, YDBPersistence) and isinstance(handler, ConversationHandler):
            # per_user=True since data in YDBPersistence is stored per user
            if not handler.per_user:
                raise ValueError('YDBPersistence requires per_user=True for ConversationHandler')
            
            # per_chat=False for simple key handling on update_data and _dump_into_json
            if handler.per_chat:
                raise ValueError('YDBPersistence requires per_chat=False for ConversationHandler')
            
            # per_message=False for simple key handling and since it's supported only when all
            # entry points and state handlers are CallbackQueryHandlers
            if handler.per_message:
                raise ValueError('YDBPersistence requires per_message=False for ConversationHandler')
            
            # Check persistence consistency
            if not handler.persistent:
                raise ValueError('ConversationHandler is not persistent')


    def load_persistence_data(
        self,
        user_id: int
        ) -> None:
        """
        Based on telegram.ext.Dispatcher.__init__.
        Allows to load user/chat/bot/callback/conversations data after initialization, e.g.
        after receiving an update without using built-in refresh_bot_data and similar functions
        """

        if self.persistence is None:
            return None
        
        elif isinstance(self.persistence, YDBPersistence):
            # Update persistence dictionaries first
            self.persistence.update_data(
                user_id=user_id,
                data=self.persistence.get_data(user_id=user_id)
            )

        if self.persistence.store_user_data:
            self.user_data = self.persistence.get_user_data()

            if not isinstance(self.user_data, defaultdict):
                raise ValueError('user_data must be of type defaultdict')

        if self.persistence.store_chat_data:
            self.chat_data = self.persistence.get_chat_data()

            if not isinstance(self.chat_data, defaultdict):
                raise ValueError('chat_data must be of type defaultdict')

        if self.persistence.store_bot_data:
            self.bot_data = self.persistence.get_bot_data()

            if not isinstance(self.bot_data, self.context_types.bot_data):
                raise ValueError(
                    f'bot_data must be of type {self.context_types.bot_data.__name__}'
                )
        
        if self.persistence.store_callback_data:
            persistent_data = self.persistence.get_callback_data()

            if persistent_data is not None:
                if not isinstance(persistent_data, tuple) and len(persistent_data) != 2:
                    raise ValueError('callback_data must be a 2-tuple')
                
                self.bot.callback_data_cache = CallbackDataCache(
                    self.bot,
                    self.bot.callback_data_cache.maxsize,
                    persistent_data=persistent_data
                )
        
        # Conversations are stored at corresponding handlers
        for group in self.groups:
            for handler in self.handlers[group]:
                if isinstance(handler, ConversationHandler) and handler.persistent:
                    handler.conversations = self.persistence.get_conversations(handler.name)

    
    def update_persistence_database(
        self,
        user_id: int,
        error: bool
        ) -> None:
        """
        Allows to save or remove persistence data after processing an update
        with only one database query
        """

        if self.persistence is None:
            return None
        
        elif isinstance(self.persistence, YDBPersistence):
            self.persistence.update_database(
                user_id=user_id,
                error=error
            )
    
    def end_conversations(
        self,
        update
        ) -> None:
        """
        End all conversations for the user in the specified update
        """

        for group in self.groups:
            for handler in self.handlers[group]:
                if isinstance(handler, ConversationHandler):
                    handler._update_state(
                        new_state=handler.END, 
                        key=handler._get_key(update)
                    )


class YDBPersistence(DictPersistence):
    """
    Persistence class for saving user and conversations data in Yandex Database.
    All data is saved per user, so it could only be used when all ConversationHandlers have
    the default setting per_user=True.
    Uses the global variable ydb_client with connection to Yandex Database
    """

    def __init__(
        self,
        **kwargs
        ):
        self.users_table = ydb_client.users_table
        self.user_id_column = ydb_client.user_id_column
        self.data_column = ydb_client.data_column
        self.meetings_ts_column = ydb_client.meetings_ts_column

        super().__init__(
            store_user_data=True,
            store_chat_data=False,
            store_bot_data=False,
            store_callback_data=False,
            **kwargs
        )


    def get_data(
        self,
        user_id: int
        ) -> dict:
        """
        Get persistent data for the specified user from the database
        """

        declarations = 'DECLARE $user_id AS Uint64;'

        query = f"""
            {declarations}
            
            SELECT {self.data_column}
            FROM {self.users_table}
            WHERE {self.user_id_column} = $user_id
        """

        parameters={
            '$user_id': user_id,
        }

        result_sets = ydb_client.execute_query(
            query=query,
            parameters=parameters
        )

        result_set = result_sets[0]

        if len(result_set.rows) < 1:
            cell = None
        
        elif len(result_set.rows) == 1:
            cell = getattr(result_set.rows[0], self.data_column)

        else:
            raise LookupError(f'Table {self.users_table} has more than 1 row for user id {user_id}')

        if cell is None:
            return {}
        
        else:
            # self.data_column is either None or a valid JSON
            return json.loads(cell)
    

    def update_data(
        self,
        user_id: int,
        data: dict
        ) -> None:
        """
        Update persistence dictionaries for the specified user with provided data
        """

        if data.get('user_data') is not None:
            self.update_user_data(
                user_id=user_id,
                data=data.get('user_data')
            )
        
        if data.get('conversations') is not None:
            for conv_name, state in data.get('conversations').items():
                self.update_conversation(
                    name=conv_name,
                    key=(user_id,),
                    new_state=state
                )


    def _dump_into_json(
        self,
        user_id: int
        ) -> str:
        """
        Dumps data for the specified user into JSON format for inserting into the database.
        Key with user_id is omitted, since it's already present in the database
        """

        to_dump = {}

        if self.user_data is not None:
            user_data = self.user_data.get(user_id)

            if user_data is not None:
                to_dump.update({
                    'user_data': user_data
                })
        
        if self.conversations is not None:
            # filter every conversation for this user_id
            conversations_data = {}

            for conv_name, conv_data in self.conversations.items():
                # Key based on settings per_user=True, per_chat=False, per_message=False
                state = conv_data.get((user_id,))

                if state is not None:
                    conversations_data.update({conv_name: state})
            
            if conversations_data:
                to_dump.update({
                    'conversations': conversations_data
                })

        return json.dumps(to_dump)


    def update_database(
        self,
        user_id: int,
        error: bool
        ) -> None:
        """
        Save or remove data for the specified user in the database
        """

        declarations = 'DECLARE $user_id AS Uint64;'

        parameters = {
            '$user_id': user_id
        }

        # Remove persistence and meetings data on error
        if error:
            query = f"""
                {declarations}
                
                UPDATE {self.users_table}
                SET {self.data_column} = NULL, {self.meetings_ts_column} = NULL
                WHERE {self.user_id_column} = $user_id
            """
        
        # Dump and save otherwise
        else:
            declarations += ' DECLARE $data AS Json;'

            data = '$data'

            parameters['$data'] = self._dump_into_json(
                user_id=user_id
            )

            query = f"""
                {declarations}
                
                UPDATE {self.users_table}
                SET {self.data_column} = {data}
                WHERE {self.user_id_column} = $user_id
            """

        ydb_client.execute_query(
            query=query,
            parameters=parameters
        )
