import logging
import os
import ujson as json
from handlers import add_handlers
from helpers import notify_developer
from persistence import (
    PersistentDispatcher,
    YDBPersistence
)
from telegram import (
    Bot,
    Update
)
from warnings import filterwarnings

# Enable logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Remove UserWarning: If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message
filterwarnings(
    action='ignore',
    message=r'.*CallbackQueryHandler'
)

# Define responses
OK_RESPONSE = {
    'statusCode': 200,
    'body': json.dumps('OK')
}

ERROR_RESPONSE = {
    'statusCode': 400,
    'body': json.dumps('ERROR')
}


def configure_telegram():
    """
    Configure a bot instance using Telegram bot token
    Return a bot instance
    """

    # Read a bot token from environment variables
    BOT_TOKEN = os.getenv('BOT_TOKEN')

    if BOT_TOKEN is None:
        raise NotImplementedError('No BOT_TOKEN found')
    
    return Bot(BOT_TOKEN)


# Initialize bot and dispatcher to register handlers
bot = configure_telegram()

dispatcher = PersistentDispatcher(
    bot=bot,
    update_queue=None,
    persistence=YDBPersistence()
)

# Add all handlers to process any received update
add_handlers(dispatcher)


def process_update(event, context):
    """
    Receive a message as an event via Telegram webhook and send a response
    """
    
    logger.info(f'Event received: {event}')

    try:
        # Convert event to an Update instance
        update = Update.de_json(
            data=json.loads(event.get('body')),
            bot=bot
        )
    
    except:
        message = f'Could not convert event {event} to an Update instance'

        logger.exception(message)
        
        notify_developer(
            message=message,
            bot=bot
        )

        return ERROR_RESPONSE

    # Load user data from the database
    dispatcher.load_persistence_data(
        user_id=update.effective_user.id
    )

    # Process received update.
    # In case of error it would be handled by handlers.on_error function
    dispatcher.process_update(update)

    unknown_update = dispatcher.user_data.get(
        update.effective_user.id, {}
    ).pop('UNKNOWN', False)
    
    error_update = dispatcher.user_data.get(
        update.effective_user.id, {}
    ).pop('ERROR', False)

    # Update persistence so we don't save these values in the database
    if unknown_update or error_update:
        dispatcher.update_persistence(update)
    
    # In case of unknown update, end all conversations
    if unknown_update:
        dispatcher.end_conversations(update)

    # Save user data back to the database
    # or remove it from the database in case of error update
    dispatcher.update_persistence_database(
        user_id=update.effective_user.id,
        error=error_update
    )

    return OK_RESPONSE
