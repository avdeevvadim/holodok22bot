import logging
import os
import ujson as json
import ydb
from typing import List

logger = logging.getLogger()


class YDBClient:
    """
    Connection to Yandex Database
    """

    def __init__(self):
        self.endpoint = os.getenv('YDB_ENDPOINT')
        self.database = os.getenv('YDB_DATABASE')
        self.users_table = 'users'
        self.likes_table = 'likes'
        self.timetable_table = 'timetable'
        self.user_id_column = 'user_id'
        self.first_name_column = 'first_name'
        self.last_name_column = 'last_name'
        self.username_column = 'username'
        self.usage_column = 'usage'
        self.data_column = 'persistence_data'
        self.meetings_ts_column = 'meetings_ts'
        self.meetings_index = 'meetings_index'
        self.likes_from_column = 'from_user_ts'
        self.likes_to_column = 'to_user_ts'
        self.likes_link_column = 'from_user_link'
        self.start_column = 'start'
        self.end_column = 'end'
        self.camp_column = 'camp'
        self.description_column = 'description'
        self.link_column = 'link'
        self.driver_timeout = 1
        self.driver = self.create_driver()
        self.pool = self.create_pool()


    def create_driver(self) -> ydb.Driver:
        """
        Create the driver that lets the app and YDB interact at the transport layer
        """

        driver = ydb.Driver(
            endpoint=self.endpoint,
            database=self.database
        )

        try:
            # Wait for the driver to become active for requests
            driver.wait(
                fail_fast=True,
                timeout=self.driver_timeout
            )
        
        except Exception:
            raise Exception(driver.discovery_debug_details())

        return driver
    
    
    def create_pool(self):
        """
        Create the session pool instance to manage YDB sessions
        """

        return ydb.SessionPool(self.driver)
    

    def execute_query(
        self,
        query,
        parameters=None
        ):
        """
        Create a transaction to YDB and execute custom query with retry
        """

        def execute(session, query, parameters):
            """
            Execute query using session from pool checkout
            """

            # Use prepared queries for safe passing user values to the query
            if parameters is not None:
                query = session.prepare(query)

            return session.transaction().execute(
                query=query,
                parameters=parameters,
                commit_tx=True
            )
        
        return self.pool.retry_operation_sync(
            callee=execute,
            query=query,
            parameters=parameters
        )


    def upsert_new_user(
        self,
        update
        ):
        """
        Add row to the database with user data, if it's not here yet.
        Don't set usage column to zero since the user may be there already
        """

        columns_string = f'{self.user_id_column}, {self.first_name_column}'
        values_string = '$user_id, $first_name'
        declarations = 'DECLARE $user_id AS Uint64; DECLARE $first_name AS Utf8;'
        parameters = {
            '$user_id': update.effective_user.id,
            '$first_name': update.effective_user.first_name
        }

        # Choose correct columns since last name and username are optional
        if update.effective_user.last_name is not None:
            columns_string += f', {self.last_name_column}'
            values_string += ', $last_name'
            declarations += ' DECLARE $last_name AS Utf8;'
            parameters['$last_name'] = update.effective_user.last_name
        
        if update.effective_user.username is not None:
            columns_string += f', {self.username_column}'
            values_string += ', $username'
            declarations += ' DECLARE $username AS Utf8;'
            parameters['$username'] = update.effective_user.username

        query = f"""
            {declarations}

            UPSERT INTO {self.users_table}
            ({columns_string})
            VALUES
            ({values_string})
        """

        self.execute_query(
            query=query,
            parameters=parameters
        )


    def update_usage(
        self,
        user_id
        ):
        """
        Increment user's bot usage data
        """

        declarations = 'DECLARE $user_id AS Uint64;'

        query = f"""
            {declarations}
            
            UPDATE {self.users_table}
            SET {self.usage_column} = COALESCE({self.usage_column}, 0) + 1
            WHERE {self.user_id_column} = $user_id
        """

        parameters={
            '$user_id': user_id
        }

        self.execute_query(
            query=query,
            parameters=parameters
        )
        

    def update_user_meetings(
        self,
        user_id,
        meetings_ts
        ):
        """
        Set or remove meetings timestamp for the specified user
        """

        declarations = 'DECLARE $user_id AS Uint64;'

        parameters = {
            '$user_id': user_id
        }

        # Set meetings timestamp if present
        if meetings_ts:
            declarations += ' DECLARE $meetings_ts AS Utf8;'

            value = 'CAST($meetings_ts AS Timestamp)'

            parameters['$meetings_ts'] = meetings_ts
        
        # Remove it otherwise
        else:
            value = 'NULL'

        query = f"""
            {declarations}
            
            UPDATE {self.users_table}
            SET {self.meetings_ts_column} = {value}
            WHERE {self.user_id_column} = $user_id
        """

        self.execute_query(
            query=query,
            parameters=parameters
        )
    
    
    def get_meetings_profile(
        self,
        after_ts,
        before_ts
        ):
        """
        Return first user profile in meetings after or before specified timestamp
        """

        if (after_ts is None) and (before_ts is None):
            parameters = None

            query = f"""
               SELECT
               COUNT(*) AS num_users,
               MAX_BY({self.data_column}, {self.meetings_ts_column}) AS user_data
               FROM {self.users_table} VIEW {self.meetings_index}
               WHERE {self.meetings_ts_column} IS NOT NULL
            """
        
        elif (after_ts is not None) and (before_ts is None):
            declarations = 'DECLARE $after_ts AS Utf8;'

            parameters={
                '$after_ts': after_ts
            }

            query = f"""
               {declarations}
            
               SELECT
               COUNT(*) AS num_users,
               MIN_BY({self.data_column}, {self.meetings_ts_column}) AS user_data
               FROM {self.users_table} VIEW {self.meetings_index}
               WHERE {self.meetings_ts_column} > CAST($after_ts AS Timestamp)
            """
        
        elif (after_ts is None) and (before_ts is not None):
            declarations = 'DECLARE $before_ts AS Utf8;'

            parameters={
                '$before_ts': before_ts
            }

            query = f"""
               {declarations}
               
               SELECT
               COUNT(*) AS num_users,
               MAX_BY({self.data_column}, {self.meetings_ts_column}) AS user_data
               FROM {self.users_table} VIEW {self.meetings_index}
               WHERE {self.meetings_ts_column} < CAST($before_ts AS Timestamp)
            """
        
        else:
            raise ValueError('after_ts and before_ts could not be not None at the same time')
        
        result_sets = self.execute_query(
            query=query,
            parameters=parameters
        )

        result_set = result_sets[0]

        num_users = getattr(result_set.rows[0], 'num_users')
        user_data = getattr(result_set.rows[0], 'user_data')

        if user_data is None:
            return num_users, {}
        
        else:
            # self.data_column is either None or a valid JSON
            return num_users, json.loads(user_data).get('user_data')
        

    def upsert_like_meetings(
        self,
        like_from_ts,
        like_to_ts,
        like_from_link
        ):
        """
        Add row to the database with likes data, if it's not here yet
        """

        declarations = """
            DECLARE $like_from_ts AS Utf8;
            DECLARE $like_to_ts AS Utf8;
            DECLARE $like_from_link AS Utf8;
        """

        query = f"""
            {declarations}

            UPSERT INTO {self.likes_table}
            ({self.likes_from_column}, {self.likes_to_column}, {self.likes_link_column})
            VALUES
            (CAST($like_from_ts AS Timestamp), CAST($like_to_ts AS Timestamp), $like_from_link)
        """

        parameters = {
            '$like_from_ts': like_from_ts,
            '$like_to_ts': like_to_ts,
            '$like_from_link': like_from_link
        }

        self.execute_query(
            query=query,
            parameters=parameters
        )
    

    def get_like_meetings(
        self,
        like_to_ts,
        ):
        """
        Get likes for the user with the specified timestamp
        """

        declarations = 'DECLARE $like_to_ts AS Utf8;'

        parameters={
            '$like_to_ts': like_to_ts
        }

        query = f"""
            {declarations}
        
            SELECT {self.likes_link_column}
            FROM {self.likes_table}
            WHERE {self.likes_to_column} = CAST($like_to_ts AS Timestamp)
        """

        result_sets = self.execute_query(
            query=query,
            parameters=parameters
        )

        result_set = result_sets[0]

        likes = []
        
        for row in result_set.rows:
            link = getattr(row, self.likes_link_column)

            likes.append(link)
        
        return likes
    
    def get_timetable(
        self,
        from_ts,
        to_ts
        ):
        """
        Get events within corresponding timestamps, one current and one next for each camp
        """

        declarations = """
            DECLARE $from_ts AS Utf8;
            DECLARE $to_ts AS Utf8;
        """

        parameters={
            '$from_ts': from_ts,
            '$to_ts': to_ts
        }

        query = f"""
            {declarations}
        
            SELECT {self.start_column}, {self.end_column}, {self.camp_column},
                   {self.description_column}, {self.link_column}, row_num
            FROM (
                SELECT {self.timetable_table}.*, ROW_NUMBER() OVER (
                    PARTITION BY {self.camp_column}
                    ORDER BY {self.start_column}
                ) AS row_num
                FROM {self.timetable_table}
                WHERE (
                    MAX_OF(
                        CAST($from_ts AS Timestamp),
                        {self.start_column}
                    ) < MIN_OF(
                        CAST($to_ts AS Timestamp),
                        {self.end_column}
                    )
                )
            )
            WHERE row_num <= 2
            ORDER BY ({self.link_column} is NULL) DESC,
                     {self.camp_column},
                     {self.end_column} - {self.start_column},
                     {self.start_column}
        """

        result_sets = self.execute_query(
            query=query,
            parameters=parameters
        )

        result_set = result_sets[0]

        return result_set.rows
        

# Create connection and use it in the next Cloud Function calls
# since serverless functions can restore context
ydb_client = YDBClient()
