import logging
import os
import sys
from telegram import (
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo
)
from telegram.error import BadRequest
from telegram.ext import MessageFilter
from telegram.utils.helpers import mention_html


logger = logging.getLogger()


class FilterMediaGroup(MessageFilter):
    """
    Custom filter for messages that are part of a media group
    """

    def filter(self, message):
        return message.media_group_id is not None

fiter_media_group = FilterMediaGroup()


def decode_entities(
    message_text,
    entities
    ):
    """
    Return original message text in HTML parse mode with given entities.
    Does not support nested entities and 'hashtag', 'cashtag', 'phone_number', 'bot_command', 'email'
    """

    if message_text is None:
        return None

    if not entities:
        return message_text

    if not sys.maxunicode == 0xffff:
        message_text = message_text.encode('utf-16-le')

    html_text = ''
    last_offset = 0

    for entity, text in sorted(entities.items(), key=(lambda item: item[0].offset)):
        if entity.type == 'bold':
            insert = f'<b>{text}</b>'
        
        elif entity.type == 'italic':
            insert = f'<i>{text}</i>'
        
        elif entity.type == 'underline':
            insert = f'<u>{text}</u>'

        elif entity.type == 'strikethrough':
            insert = f'<s>{text}</s>'
        
        elif entity.type == 'spoiler':
            insert = f'<tg-spoiler>{text}</tg-spoiler>'

        elif entity.type == 'url':
            insert = f'<a href="{text}">{text}</a>'
        
        elif entity.type == 'mention':
            insert = f'<a href="https://t.me/{text.strip("@")}">{text}</a>'

        elif (entity.type == 'text_link') and (entity.url is not None):
            insert = f'<a href="{entity.url}">{text}</a>'
        
        elif (entity.type == 'text_mention') and (entity.user is not None):
            insert = f'<a href="tg://user?id={entity.user.id}">{text}</a>'
        
        elif entity.type == 'code':
            insert = f'<code>{text}</code>'
        
        elif (entity.type == 'pre') and (entity.language is None):
            insert = f'<pre>{text}</pre>'

        elif (entity.type == 'pre') and (entity.language is not None):
            insert = f'<pre><code class="{entity.language}">{text}</code></pre>'
        
        else:
            insert = text
        
        if sys.maxunicode == 0xffff:
            html_text += message_text[last_offset : entity.offset] + insert
        
        else:
            html_text += message_text[last_offset * 2:entity.offset * 2].decode('utf-16-le') + insert

        last_offset = entity.offset + entity.length

    if sys.maxunicode == 0xffff:
        html_text += message_text[last_offset:]
    
    else:
        html_text += message_text[last_offset * 2:].decode('utf-16-le')
    
    return html_text


def notify_developer(
    message='Some error occured!',
    bot=None,
    context=None
    ):
    """
    Send a message to the developer, for example, about an error.
    Either bot or context should not be None
    """

    if bot is None:
        bot = context.bot

    try:
        bot.send_message(
            chat_id=os.getenv('DEVELOPER_ID'),
            text=message,
            parse_mode='HTML'
        )

    except:
        logger.exception(f'Could not send to the developer the message: {message}')


def reply_message(
    update,
    context,
    text=None,
    media=None,
    reply_markup=None,
    parse_mode=None,
    disable_web_page_preview=None
    ):
    """
    Reply to user with either text or media message
    """

    try:
        if text is not None:
            update.effective_message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
        
        elif isinstance(media, InputMediaAnimation):
            update.effective_message.reply_animation(
                animation=media.media,
                caption=getattr(media, 'caption', None),
                reply_markup=reply_markup,
                parse_mode=getattr(media, 'parse_mode', None)
            )
        
        elif isinstance(media, InputMediaAudio):
            update.effective_message.reply_audio(
                audio=media.media,
                caption=getattr(media, 'caption', None),
                reply_markup=reply_markup,
                parse_mode=getattr(media, 'parse_mode', None)
            )

        elif isinstance(media, InputMediaDocument):
            update.effective_message.reply_document(
                document=media.media,
                caption=getattr(media, 'caption', None),
                reply_markup=reply_markup,
                parse_mode=getattr(media, 'parse_mode', None)
            )

        elif isinstance(media, InputMediaPhoto):
            update.effective_message.reply_photo(
                photo=media.media,
                caption=getattr(media, 'caption', None),
                reply_markup=reply_markup,
                parse_mode=getattr(media, 'parse_mode', None)
            )
        
        elif isinstance(media, InputMediaVideo):
            update.effective_message.reply_video(
                video=media.media,
                caption=getattr(media, 'caption', None),
                reply_markup=reply_markup,
                parse_mode=getattr(media, 'parse_mode', None)
            )
        
        else:
            notify_developer(
                text=f'Unknown message type, media = {media}, message = {update.effective_message}',
                context=context
            )
    
    except Exception as exception:
        logger.warning(f'Encountered telegram.error: {exception}')

        # In case of time out do nothing
        if 'Timed out' in str(exception):
            pass
        
        else:
            raise exception


def reply_or_edit_message(
    update,
    context,
    text=None,
    media=None,
    reply_markup=None,
    parse_mode=None,
    disable_web_page_preview=None,
    force_new_message=False
    ):
    """
    Check whether it's a callback query which means we can edit
    message instead of sending a new one if they are of the same type
    """

    # If update is neither callback or message, e.g. a stop command to bot, do nothing
    if (update.callback_query is None) and (update.effective_message is None):
        return None
    
    # If there is no callback, send a new message and exit
    if update.callback_query is None:
        return reply_message(
            update=update,
            context=context,
            text=text,
            media=media,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
    
    # Otherwise try to answer callback query
    try:
        update.callback_query.answer()

    except:
        pass

    # If we specifically asked to send a new message, do it and exit
    if force_new_message:
        return reply_message(
            update=update,
            context=context,
            text=text,
            media=media,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )

    # Otherwise if both previous and new messages are text, edit message
    if (update.callback_query.message.text is not None) and (text is not None) and (media is None):
        try:
            update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
        
        except Exception as exception:
            logger.warning(f'Encountered telegram.error: {exception}')

            # In case message is not modified or time out do nothing
            if (
                ('Message is not modified' in str(exception)) or
                ('Timed out' in str(exception))
            ):
                pass
            
            # In case of error (message not found / query is too old or invalid / etc)
            # try to send a new message instead
            else:
                reply_message(
                    update=update,
                    context=context,
                    text=text,
                    media=media,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
    
    # If both previous and new messages are media, edit message
    elif (update.callback_query.message.text is None) and (text is None) and (media is not None):
        try:
            update.callback_query.edit_message_media(
                media=media,
                reply_markup=reply_markup
            )
        
        except Exception as exception:
            logger.warning(f'Encountered telegram.error: {exception}')

            # In case message is not modified do nothing
            if (
                ('Message is not modified' in str(exception)) or
                ('Timed out' in str(exception))
            ):
                pass
            
            # In case of error (message not found / query is too old or invalid / etc)
            # try to send a new message instead
            else:
                reply_message(
                    update=update,
                    context=context,
                    text=text,
                    media=media,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
    
    # If we need to transform text message to media one, remove the previos message and send the new one
    elif (update.callback_query.message.text is not None) and (text is None) and (media is not None):
        # Try to remove the previous one
        try:
            update.callback_query.delete_message()
        
        except:
            pass
        
        # Send a new one
        reply_message(
            update=update,
            context=context,
            text=text,
            media=media,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
    
    # If we need to transform media message to text one, remove the previos message and send the new one
    elif (update.callback_query.message.text is None) and (text is not None) and (media is None):
        # Try to remove the previous one
        try:
            update.callback_query.delete_message()
        
        except:
            pass

        reply_message(
            update=update,
            context=context,
            text=text,
            media=media,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
    
    else:
        raise ValueError(
            f'update.callback_query.message = {update.callback_query.message}, '
            f'text = {text}, media = {media}'
        )
