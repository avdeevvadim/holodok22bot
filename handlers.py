import datetime as dt
import html
import logging
import os
import random
import traceback
import ujson as json
from collections import namedtuple
from database import ydb_client
from helpers import (
    decode_entities,
    fiter_media_group,
    notify_developer,
    reply_or_edit_message
)
from paginator import InlineKeyboardPaginator
from static_data import (
    camps_data,
    memes_data,
    principles_data,
    principles_description
)
from telegram import (
    constants,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Update
)
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackQueryHandler,
    TypeHandler
)
from telegram.utils.helpers import mention_html
from zoneinfo import ZoneInfo

timezone = ZoneInfo('Europe/Moscow')
logger = logging.getLogger()

# Constants for ConversationHandler states
StatesHolder = namedtuple('StatesHolder', [
    'POST_CHANNEL_GET_MESSAGE',
    'POST_CHANNEL_GET_PRIVACY',
    'POST_CHANNEL_GET_SENDING_CONFIRMATION',
    'MEETINGS_GET_NAME',
    'MEETINGS_GET_PHOTO',
    'MEETINGS_GET_BIO',
    'MEETINGS_GET_CHANGE_CONFIRMATION',
    'MEETINGS_GET_PARTICIPATION_CONFIRMATION',
    'MEETINGS_GET_REMOVAL_CONFIRMATION',
    'MEETINGS_CHOOSE_ACTION',
    'MEETINGS_CHOOSE_PERSON_ACTION',
    'MORTUARY_CHOOSE_ACTION',
    'PRINCIPLES_CHOOSE_ACTION',
    'END' # Shortcut for ConversationHandler.END, should be the last one
])

# Set constant values to their names, except for the last one
states = StatesHolder(*StatesHolder._fields[:-1], ConversationHandler.END)

# Constants for InlineKeyboardButton callback data
CallbackHolder = namedtuple('CallbackHolder', [
    'POST_CHANNEL_START',
    'POST_CHANNEL_PUBLIC',
    'POST_CHANNEL_PRIVATE',
    'POST_CHANNEL_CONFIRM_SENDING',
    'POST_CHANNEL_STOP',
    'MEETINGS_START',
    'MEETINGS_CONFIRM_PARTICIPATION',
    'MEETINGS_SHOW_PEOPLE',
    'MEETINGS_SHOW_PEOPLE_LEFT',
    'MEETINGS_SHOW_PEOPLE_RIGHT',
    'MEETINGS_SHOW_LIKES',
    'MEETINGS_LIKE',
    'MEETINGS_CHANGE',
    'MEETINGS_CONFIRM_CHANGE',
    'MEETINGS_REMOVE',
    'MEETINGS_CONFIRM_REMOVAL',
    'MEETINGS_STOP',
    'CAMPS_START',
    'CAMPS_STOP',
    'TIMETABLE_START',
    'TIMETABLE_STOP',
    'MAP_START',
    'MAP_STOP',
    'SHUTTLE_START',
    'SHUTTLE_STOP',
    'SHELTER_START',
    'SHELTER_STOP',
    'MORTUARY_START',
    'MORTUARY_SHOW_MEME',
    'MORTUARY_START_OVER',
    'MORTUARY_STOP',
    'PRINCIPLES_START',
    'PRINCIPLES_PAGE',
    'PRINCIPLES_STOP',
    'SOS_START',
    'SOS_STOP'
])

callbacks = CallbackHolder(*CallbackHolder._fields)

# Constants for supported message types to publish in the board channel
TypesHolder = namedtuple('TypesHolder', [
    'ANIMATION',
    'AUDIO',
    'DOCUMENT',
    'PHOTO',
    'TEXT',
    'VIDEO'
])

types = TypesHolder(*TypesHolder._fields)

# Telegram limits for maximum both first and last names
# Missing in telegram.constants
MAX_NAME_LENGTH = 64

# Period in the timetable, from the current timestamp to the next number of hours
TIMETABLE_PERIOD_HOURS = 2


def on_start(update, context):
    """
    Send a message when the command /start is issued
    """

    on_help(update, context)

    on_top(update, context)
    
    ydb_client.upsert_new_user(update=update)


def on_help(update, context):
    """
    Send help message when the command /help is issued
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Давай расскажу, что я умею!\n\n'
            f'Во-первых, через меня ты можешь написать в <a href="{os.getenv("BOARD_LINK")}">общий канал</a> Холодка. '
            'В нем можно найти актуальную геопозицию шаттла между «Дружбой» и «Зеленым городком», разные объявления, '
            'а также привязанную к нему группу для комментирования постов в канале.\n\n'
            'Во-вторых, здесь можно познакомиться с другими участниками Холодка! Для этого необходимо '
            'заполнить немного информации о себе и затем договориться о встрече. А еще там можно ставить и получать лайки :)\n\n'
            'В-третьих, у нас собрана информация о всех лагерях Холодка и даже расписание их событий, которое мы показываем '
            'на ближайшие два часа. Теперь можно легко понять, пора идти завтракать или уже обедать.\n\n'
            'Также здесь можно найти карту Холодка в двух вариантах, ссылку на радио ШалашFM, мемы на тему смерти от лагеря '
            '«ПогребальНЯ и Душный бар», 10 принципов Burning Man, по которым живет наше сообщество, и телефон для экстренной связи со штабом'
        ),
        parse_mode='HTML'
    )


def on_top(
    update,
    context,
    text='Что хочешь сделать?',
    media=None,
    reply_markup=None,
    parse_mode=None,
    disable_web_page_preview=None,
    force_new_message=False
    ):
    """
    Send a reply with top-level keyboard when receiving a password
    or returning to top-level menu
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=text,
        media=media,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Написать в канал',
                        callback_data=callbacks.POST_CHANNEL_START
                    ),
                    InlineKeyboardButton(
                        text='Познакомиться',
                        callback_data=callbacks.MEETINGS_START
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text='Почитать о кэмпах',
                        callback_data=callbacks.CAMPS_START
                    ),
                    InlineKeyboardButton(
                        text='Узнать расписание',
                        callback_data=callbacks.TIMETABLE_START
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text='Посмотреть на карту',
                        callback_data=callbacks.MAP_START
                    ),
                    InlineKeyboardButton(
                        text='Найти шаттл',
                        callback_data=callbacks.SHUTTLE_START
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text='Послушать ШалашFM',
                        callback_data=callbacks.SHELTER_START
                    ),
                    InlineKeyboardButton(
                        text='Умереть от смеха',
                        callback_data=callbacks.MORTUARY_START
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text='Вспомнить принципы',
                        callback_data=callbacks.PRINCIPLES_START
                    ),
                    InlineKeyboardButton(
                        text='Позвать на помощь',
                        callback_data=callbacks.SOS_START
                    ),
                ]
            ],
            resize_keyboard=True
        ),
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
        force_new_message=force_new_message
    )


def post_channel_start(update, context):
    """
    Ask for a message to post in the board channel and prepare the message footer
    """

    # Construct user full name and message footer and save it for later usage
    full_name = f'{update.effective_user.first_name}'

    if update.effective_user.last_name is not None:
        full_name += f' {update.effective_user.last_name}'
    
    context.user_data['post_channel_public_footer'] = f'\n\n — {mention_html(update.effective_user.id, full_name)}'

    context.user_data['post_channel_private_footer'] = f'\n\n — Аноним'

    context.user_data['post_channel_footer_max_length'] = max(
        len(context.user_data['post_channel_public_footer']),
        len(context.user_data['post_channel_private_footer'])
    )

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            f'Напиши мне сообщение, которое нужно отправить в общий <a href="{os.getenv("BOARD_LINK")}">канал</a>.\n\n'
            'Например, объявление о том, что у вас сейчас начинается классная активность, '
            'просьбу помочь что-то найти, или даже признание в любви! Мемы тоже годятся :)\n\n'
            'Отправить сообщение можно от своего имени или анонимно. '
            'Это может быть текстовое сообщение или медиа с подписью или без (например, фото или видео), но не альбом из них.'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.POST_CHANNEL_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        parse_mode='HTML'
    )

    return states.POST_CHANNEL_GET_MESSAGE


def post_channel_message(update, context):
    """
    Check a message length from the user to post it in the board channel
    """

    user_length = 0
    max_length = constants.MAX_CAPTION_LENGTH

    if update.message.text is not None:
        user_length = len(update.message.text)
        max_length = constants.MAX_MESSAGE_LENGTH
    
    elif update.message.caption is not None:
        user_length = len(update.message.caption)
        max_length = constants.MAX_CAPTION_LENGTH

    # In fact max length depends on formatting, but let's simplify it here
    if user_length + context.user_data['post_channel_footer_max_length'] > max_length:
        # Ask for another message
        return post_channeltoo_long(update, context)
    
    # Save user message or caption with entities decoded to HTML if present
    if update.message.text is not None:
        entities = update.message.parse_entities()

        context.user_data['post_channel_message'] = decode_entities(
            message_text=update.message.text,
            entities=entities
        )
    
    elif update.message.caption is not None:
        entities = update.message.parse_caption_entities()

        context.user_data['post_channel_message'] = decode_entities(
            message_text=update.message.caption,
            entities=entities
        )
    
    else:
        context.user_data['post_channel_message'] = ''

    # Save user message type and file if present
    if update.message.text is not None:
        context.user_data['post_channel_message_type'] = types.TEXT
    
    # Animation should be checked before document
    elif update.message.animation is not None:
        context.user_data['post_channel_message_type'] = types.ANIMATION
        context.user_data['post_channel_file_id'] = update.message.animation.file_id

    elif update.message.audio is not None:
        context.user_data['post_channel_message_type'] = types.AUDIO
        context.user_data['post_channel_file_id'] = update.message.audio.file_id

    elif update.message.document is not None:
        context.user_data['post_channel_message_type'] = types.DOCUMENT
        context.user_data['post_channel_file_id'] = update.message.document.file_id

    # Photo attribute is a possibly empty list
    elif update.message.photo:
        context.user_data['post_channel_message_type'] = types.PHOTO
        # Photo is a list of telegram.PhotoSize with available sizes of the photo
        context.user_data['post_channel_file_id'] = update.message.photo[0].file_id

    elif update.message.video is not None:
        context.user_data['post_channel_message_type'] = types.VIDEO
        context.user_data['post_channel_file_id'] = update.message.video.file_id

    elif update.message.voice is not None:
        context.user_data['post_channel_message_type'] = types.VOICE
        context.user_data['post_channel_file_id'] = update.message.voice.file_id
    
    else:
        return on_unknown(update, context)
    
    # Ask for privacy settings
    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Отлично, будем посылать сообщение в канал от твоего имени или анонимно?'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='От меня',
                        callback_data=callbacks.POST_CHANNEL_PUBLIC
                    ),
                    InlineKeyboardButton(
                        text='Анонимно',
                        callback_data=callbacks.POST_CHANNEL_PRIVATE
                    ),
                    InlineKeyboardButton(
                        text='Отмена',
                        callback_data=callbacks.POST_CHANNEL_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )
    
    return states.POST_CHANNEL_GET_PRIVACY


def post_channel_privacy(update, context):
    """
    Show user its message and ask if they are sure to post it in the board channel
    """

    full_message = context.user_data.get('post_channel_message', '')

    if update.callback_query.data == callbacks.POST_CHANNEL_PUBLIC:
        full_message += context.user_data.get('post_channel_public_footer', '')
    
    elif update.callback_query.data == callbacks.POST_CHANNEL_PRIVATE:
        full_message += context.user_data.get('post_channel_private_footer', '')
    
    context.user_data['post_channel_full_message'] = full_message

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Хорошо, вот так будет выглядеть твое сообщение для всех участников:'
        )
    )

    if context.user_data.get('post_channel_message_type') == types.ANIMATION:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaAnimation(
                media=context.user_data.get('post_channel_file_id'),
                caption=full_message,
                parse_mode='HTML'
            ),
            force_new_message=True
        )
    
    elif context.user_data.get('post_channel_message_type') == types.AUDIO:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaAudio(
                media=context.user_data.get('post_channel_file_id'),
                caption=full_message,
                parse_mode='HTML'
            ),
            force_new_message=True
        )

    elif context.user_data.get('post_channel_message_type') == types.DOCUMENT:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaDocument(
                media=context.user_data.get('post_channel_file_id'),
                caption=full_message,
                parse_mode='HTML'
            ),
            force_new_message=True
        )
    
    elif context.user_data.get('post_channel_message_type') == types.PHOTO:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaPhoto(
                media=context.user_data.get('post_channel_file_id'),
                caption=full_message,
                parse_mode='HTML'
            ),
            force_new_message=True
        )
    
    elif context.user_data.get('post_channel_message_type') == types.TEXT:
        reply_or_edit_message(
            update=update,
            context=context,
            text=full_message,
            parse_mode='HTML',
            force_new_message=True
        )
    
    elif context.user_data.get('post_channel_message_type') == types.VIDEO:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaVideo(
                media=context.user_data.get('post_channel_file_id'),
                caption=full_message,
                parse_mode='HTML'
            ),
            force_new_message=True
        )
    
    else:
        return on_unknown(update, context)

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Отправляем?'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Да!',
                        callback_data=callbacks.POST_CHANNEL_CONFIRM_SENDING
                    ),
                    InlineKeyboardButton(
                        text='Нет 💁‍♂️',
                        callback_data=callbacks.POST_CHANNEL_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        force_new_message=True
    )

    return states.POST_CHANNEL_GET_SENDING_CONFIRMATION


def post_channel_confirm_sending(update, context):
    """
    Send a message to the board channel based on privacy settings
    """
    
    # Send message to the channel
    if context.user_data.get('post_channel_message_type') == types.ANIMATION:
        context.bot.send_animation(
            chat_id=os.getenv('BOARD_ID'),
            animation=context.user_data.get('post_channel_file_id'),
            caption=context.user_data.get('post_channel_full_message'),
            parse_mode='HTML'
        )
    
    elif context.user_data.get('post_channel_message_type') == types.AUDIO:
        context.bot.send_audio(
            chat_id=os.getenv('BOARD_ID'),
            audio=context.user_data.get('post_channel_file_id'),
            caption=context.user_data.get('post_channel_full_message'),
            parse_mode='HTML'
        )

    elif context.user_data.get('post_channel_message_type') == types.DOCUMENT:
        context.bot.send_document(
            chat_id=os.getenv('BOARD_ID'),
            document=context.user_data.get('post_channel_file_id'),
            caption=context.user_data.get('post_channel_full_message'),
            parse_mode='HTML'
        )
    
    elif context.user_data.get('post_channel_message_type') == types.PHOTO:
        context.bot.send_photo(
            chat_id=os.getenv('BOARD_ID'),
            photo=context.user_data.get('post_channel_file_id'),
            caption=context.user_data.get('post_channel_full_message'),
            parse_mode='HTML'
        )
    
    elif context.user_data.get('post_channel_message_type') == types.TEXT:
        context.bot.send_message(
            chat_id=os.getenv('BOARD_ID'),
            text=context.user_data.get('post_channel_full_message'),
            parse_mode='HTML'
        )
    
    elif context.user_data.get('post_channel_message_type') == types.VIDEO:
        context.bot.send_video(
            chat_id=os.getenv('BOARD_ID'),
            video=context.user_data.get('post_channel_file_id'),
            caption=context.user_data.get('post_channel_full_message'),
            parse_mode='HTML'
        )
    
    else:
        return on_unknown(update, context)
    
    # Send message to the user
    on_top(
        update=update,
        context=context,
        text=(
            f'<a href="{os.getenv("BOARD_LINK")}">Готово!</a>\n\n'
            'Что хочешь сделать теперь?'
        ),
        parse_mode='HTML'
    )

    # Remove post channel data if present
    context.user_data.pop('post_channel_message', None)
    context.user_data.pop('post_channel_message_type', None)
    context.user_data.pop('post_channel_file_id', None)
    context.user_data.pop('post_channel_full_message', None)
    context.user_data.pop('post_channel_public_footer', None)
    context.user_data.pop('post_channel_private_footer', None)
    context.user_data.pop('post_channel_footer_max_length', None)

    return states.END


def post_channel_stop(update, context):
    """
    End conversation and return to top-level menu
    """

    on_top(update, context)

    # Remove post channel data if present
    context.user_data.pop('post_channel_message', None)
    context.user_data.pop('post_channel_message_type', None)
    context.user_data.pop('post_channel_file_id', None)
    context.user_data.pop('post_channel_full_message', None)
    context.user_data.pop('post_channel_public_footer', None)
    context.user_data.pop('post_channel_private_footer', None)
    context.user_data.pop('post_channel_footer_max_length', None)

    return states.END


def post_channeltoo_long(update, context):
    """
    Ask for another shorter message to post in the board channel
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Чересчур длинное у тебя сообщение получилось. Попробуй написать еще раз покороче'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Отмена',
                        callback_data=callbacks.POST_CHANNEL_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )

    # Remove message data if present
    context.user_data.pop('post_channel_message', None)
    context.user_data.pop('post_channel_message_type', None)
    context.user_data.pop('post_channel_file_id', None)
    context.user_data.pop('post_channel_full_message', None)

    return states.POST_CHANNEL_GET_MESSAGE


def meetings_start(update, context, text=None):
    """
    Ask user his name to participate in meetings or show a menu
    if they are already participating
    """

    if context.user_data.get('in_meetings'):
        if text is None:
            text = 'Что хочешь сделать?'
        
        reply_or_edit_message(
            update=update,
            context=context,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text='Посмотреть на всех',
                            callback_data=callbacks.MEETINGS_SHOW_PEOPLE
                        ),
                        InlineKeyboardButton(
                            text='Посмотреть на лайки',
                            callback_data=callbacks.MEETINGS_SHOW_LIKES
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text='Изменить информацию',
                            callback_data=callbacks.MEETINGS_CHANGE
                        ),
                        InlineKeyboardButton(
                            text='Прекратить участие',
                            callback_data=callbacks.MEETINGS_REMOVE
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text='Назад',
                            callback_data=callbacks.MEETINGS_STOP
                        )
                    ]
                ],
                resize_keyboard=True
            )
        )

        return states.MEETINGS_CHOOSE_ACTION

    else:
        reply_or_edit_message(
            update=update,
            context=context,
            text=(
                'Чтобы найти новые знакомства на Холодке, сначала необходимо зарегистрироваться — '
                'написать свое имя и пару слов о себе, а также приложить свое фото или видео, чтобы остальные '
                'участники могли тебя узнать. После этого можно будет посмотреть на всех остальных и даже поставить '
                'кому-нибудь лайк!\n\n'
                'Для начала напиши, как тебя зовут?'
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text='Назад',
                            callback_data=callbacks.MEETINGS_STOP
                        )
                    ]
                ],
                resize_keyboard=True
            )
        )
        
        return states.MEETINGS_GET_NAME


def meetings_name(update, context):
    """
    Save user name and ask them photo or video to participate in meetings
    """

    if update.message.text is None:
        return on_unknown(update, context)
    
    elif len(update.message.text) > 2 * MAX_NAME_LENGTH:
        return meetings_name_too_long(update, context)
    
    else:
        context.user_data['meetings_name'] = update.message.text

        context.user_data['meetings_link'] = mention_html(
            update.effective_user.id,
            context.user_data['meetings_name']
        )

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Отлично, теперь пришли свое фото или видео (но не альбом из них)'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Отмена',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )
    
    return states.MEETINGS_GET_PHOTO


def meetings_photo(update, context):
    """
    Save user photo and ask them for bio to participate in meetings
    """

    # Photo attribute is a possibly empty list
    if update.message.photo:
        context.user_data['meetings_file_type'] = types.PHOTO
        # Photo is a list of telegram.PhotoSize with available sizes of the photo
        context.user_data['meetings_file_id'] = update.message.photo[0].file_id

    elif update.message.video is not None:
        context.user_data['meetings_file_type'] = types.VIDEO
        context.user_data['meetings_file_id'] = update.message.video.file_id
    
    else:
        return on_unknown(update, context)
    
    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'И наконец, расскажи немного о себе'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Отмена',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )
    
    return states.MEETINGS_GET_BIO


def show_user_profile(update, context, force_new_message):
    """
    Send user it's current meetings profile
    """

    if context.user_data.get('meetings_file_type') == types.PHOTO:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaPhoto(
                media=context.user_data.get('meetings_file_id'),
                caption=context.user_data.get('meetings_caption'),
                parse_mode='HTML'
            ),
            force_new_message=force_new_message
        )
    
    elif context.user_data.get('meetings_file_type') == types.VIDEO:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaVideo(
                media=context.user_data.get('meetings_file_id'),
                caption=context.user_data.get('meetings_caption'),
                parse_mode='HTML'
            ),
            force_new_message=force_new_message
        )
    
    else:
        on_unknown(update, context)

        raise ValueError()


def meetings_bio(update, context):
    """
    Check bio, save it, show all data back to the user and ask for approve
    """

    if (update.message.text is None) or (context.user_data.get('meetings_name') is None):
        return on_unknown(update, context)

    meetings_caption = (
        f'\n\n{update.message.text}'
        f'\n\n — {context.user_data["meetings_link"]}'
    )

    # In fact max length depends on formatting, but let's simplify it here
    if len(meetings_caption) > constants.MAX_CAPTION_LENGTH:
        # Ask for another bio
        return meetings_bio_too_long(update, context)
    
    else:
        context.user_data['meetings_bio'] = update.message.text
        context.user_data['meetings_caption'] = meetings_caption

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Отлично, так тебя будут видеть другие участники:'
        )
    )

    show_user_profile(
        update=update,
        context=context,
        force_new_message=True
    )

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Всё норм, подтверждаешь?'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Да!',
                        callback_data=callbacks.MEETINGS_CONFIRM_PARTICIPATION
                    ),
                    InlineKeyboardButton(
                        text='Нет 💁‍♂️',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        force_new_message=True
    )
    
    return states.MEETINGS_GET_PARTICIPATION_CONFIRMATION


def meetings_confirm_participation(update, context):
    """
    Save user meetings data to the database
    """

    context.user_data['in_meetings'] = True

    # Get current time with actual timezone and convert it to string
    # with format required by YDB
    context.user_data['meetings_ts'] = dt.datetime.now(
        tz=timezone
    ).replace(
        tzinfo=None
    ).isoformat(
        timespec='microseconds'
    ) + 'Z'

    ydb_client.update_user_meetings(
        user_id=update.effective_user.id,
        meetings_ts=context.user_data['meetings_ts']
    )

    return meetings_start(
        update=update,
        context=context,
        text=(
            f'Готово!\n\n'
            'Что хочешь сделать теперь?'
        )
    )


def meetings_show_people(
    update,
    context,
    after_ts=None,
    before_ts=None
    ):
    """
    Show user some profile in meetings based on corresponding timestamp of another profile
    """

    # Get number of users after or before the corresponding timestamp
    # and the profile of first or last of them
    num_users, user_data = ydb_client.get_meetings_profile(
        after_ts=after_ts,
        before_ts=before_ts
    )

    if num_users == 0:
        on_top(
            update=update,
            context=context,
            text='Пока еще никто не зарегистрировался.\n\nЧто хочешь сделать теперь?'
        )

        return states.END
    
    elif user_data.get('meetings_file_type') == types.PHOTO:
        media = InputMediaPhoto(
            media=user_data.get('meetings_file_id'),
            caption=user_data.get('meetings_caption'),
            parse_mode='HTML'
        )
    
    elif user_data.get('meetings_file_type') == types.VIDEO:
        media = InputMediaVideo(
            media=user_data.get('meetings_file_id'),
            caption=user_data.get('meetings_caption'),
            parse_mode='HTML'
        )
    
    else:
        on_top(
            update=update,
            context=context,
            text=(
                'Что-то пошло не так, давай попробуем еще раз.\n\n'
                'Что хочешь сделать теперь?'
            )
        )

        return states.END
    
    context.user_data['current_meetings_ts'] = user_data.get('meetings_ts')
    
    # Check what buttons should be on the menu
    left_button = False
    right_button = False

    if (after_ts is None) and (before_ts is None):
        if num_users > 1:
            right_button = True
    
    elif (after_ts is not None) and (before_ts is None):
        right_button = True

        if num_users > 1:
            left_button = True
    
    elif (after_ts is None) and (before_ts is not None):
        left_button = True

        if num_users > 1:
            right_button = True

    else:
        raise ValueError('after_ts and before_ts could not be not None at the same time')
    
    # Build left and right buttons for menu if needed
    if left_button and right_button:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='‹',
                        callback_data=callbacks.MEETINGS_SHOW_PEOPLE_LEFT
                    ),
                    InlineKeyboardButton(
                        text='·💜·',
                        callback_data=callbacks.MEETINGS_LIKE
                    ),
                    InlineKeyboardButton(
                        text='›',
                        callback_data=callbacks.MEETINGS_SHOW_PEOPLE_RIGHT
                    ),
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    
    elif left_button:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='‹',
                        callback_data=callbacks.MEETINGS_SHOW_PEOPLE_LEFT
                    ),
                    InlineKeyboardButton(
                        text='·💜·',
                        callback_data=callbacks.MEETINGS_LIKE
                    ),
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    
    elif right_button:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='·💜·',
                        callback_data=callbacks.MEETINGS_LIKE
                    ),
                    InlineKeyboardButton(
                        text='›',
                        callback_data=callbacks.MEETINGS_SHOW_PEOPLE_RIGHT
                    ),
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    
    else:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    
    # Send profile and buttons
    reply_or_edit_message(
        update=update,
        context=context,
        media=media,
        reply_markup=reply_markup
    )
    
    return states.MEETINGS_CHOOSE_PERSON_ACTION


def meetings_show_people_left(update, context):
    """
    Show user the previous profile in meetings
    """

    return meetings_show_people(
        update=update,
        context=context,
        after_ts=context.user_data['current_meetings_ts'],
        before_ts=None
    )


def meetings_show_people_right(update, context):
    """
    Show user the next profile in meetings
    """

    return meetings_show_people(
        update=update,
        context=context,
        after_ts=None,
        before_ts=context.user_data['current_meetings_ts']
    )


def meetings_like(update, context):
    """
    Save user like and say user about that
    """

    ydb_client.upsert_like_meetings(
        like_from_ts=context.user_data.get('meetings_ts'),
        like_to_ts=context.user_data.get('current_meetings_ts'),
        like_from_link=context.user_data.get('meetings_link')
    )

    try:
        update.callback_query.answer('Лайк записан!')
    
    except:
        pass

    return states.MEETINGS_CHOOSE_PERSON_ACTION


def meetings_show_likes(update, context):
    """
    Send user a message with list of all likes they received and end conversation
    """

    likes = ydb_client.get_like_meetings(
        like_to_ts=context.user_data.get('meetings_ts')
    )

    message = (
        'Вот кто уже успел поставить тебе лайк:\n\n' + \
        '\n\n'.join(likes) + \
        '\n\nЧто хочешь сделать теперь?'
    )

    if len(message) > constants.MAX_MESSAGE_LENGTH:
        message = (
            'Тебе поставили уже столько лайков, что они не умещаются в одно сообщение! 😱\n\n'
            'Поэтому покажу только тех, кто в него уместился:\n\n' + \
            '\n\n'.join(likes)
        )[:constants.MAX_MESSAGE_LENGTH - len('\n\nЧто хочешь сделать теперь?')].rpartition('\n\n')[0]

        message += '\n\nЧто хочешь сделать теперь?'

    if likes:
        on_top(
            update=update,
            context=context,
            text=message,
            parse_mode='HTML'
        )
    
    else:
        on_top(
            update=update,
            context=context,
            text=(
                'Пока лайков не было, но скоро они наверняка появятся!\n\n'
                'Что хочешь сделать теперь?'
            )
        )
    
    return states.END


def meetings_change(update, context):
    """
    Show user its current profile and ask if it wants to change it
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Вот как сейчас выглядит твой профиль для других участников:'
        )
    )

    show_user_profile(
        update=update,
        context=context,
        force_new_message=True
    )

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Точно хочешь его поменять?'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Да!',
                        callback_data=callbacks.MEETINGS_CONFIRM_CHANGE
                    ),
                    InlineKeyboardButton(
                        text='Нет 💁‍♂️',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        force_new_message=True
    )

    return states.MEETINGS_GET_CHANGE_CONFIRMATION


def meetings_confirm_change(update, context):
    """
    Ask user its name once again
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Хорошо, для начала напиши, как тебя зовут?'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Отмена',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )
    
    return states.MEETINGS_GET_NAME


def meetings_remove(update, context):
    """
    Ask user if they are sure to stop participating in meetings
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Точно хочешь прекратить участие в знакомствах?'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Да!',
                        callback_data=callbacks.MEETINGS_CONFIRM_REMOVAL
                    ),
                    InlineKeyboardButton(
                        text='Нет 💁‍♂️',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )

    return states.MEETINGS_GET_REMOVAL_CONFIRMATION


def meetings_confirm_removal(update, context):
    """
    Remove user data and update user status in the database
    """

    context.user_data['in_meetings'] = False

    ydb_client.update_user_meetings(
        user_id=update.effective_user.id,
        meetings_ts=False
    )

    on_top(
        update=update,
        context=context,
        text=(
            'Готово!\n\n'
            'Что хочешь сделать теперь?'
        )
    )

    context.user_data.pop('meetings_name', None)
    context.user_data.pop('meetings_link', None)
    context.user_data.pop('meetings_file_type', None)
    context.user_data.pop('meetings_file_id', None)
    context.user_data.pop('meetings_bio', None)
    context.user_data.pop('meetings_caption', None)
    context.user_data.pop('meetings_ts', None)

    return states.END


def meetings_stop(update, context):
    """
    End conversation and return to top-level menu
    """

    on_top(update, context)

    return states.END


def meetings_name_too_long(update, context):
    """
    Ask for another shorter name to participate in meetings
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Чересчур длинное у тебя имя получилось. Попробуй написать еще раз покороче'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Отмена',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )

    return states.MEETINGS_GET_NAME


def meetings_bio_too_long(update, context):
    """
    Ask for another shorter bio to participate in meetings
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Чересчур длинное у тебя описание получилось. Попробуй написать еще раз покороче'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Отмена',
                        callback_data=callbacks.MEETINGS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )

    return states.MEETINGS_GET_BIO


def camps_start(update, context):
    """
    Show camps description
    """

    message_1 = (
        'Список всех лагерей на Холодке вместе с их описаниями:\n\n•' + \
        '\n•'.join(map(lambda camp: f'<a href="{camp[1]}">{camp[0]}</a>', camps_data[:len(camps_data) // 2]))
    )

    message_2 = (
        '•' + \
        '\n•'.join(map(lambda camp: f'<a href="{camp[1]}">{camp[0]}</a>', camps_data[len(camps_data) // 2:]))
    )


    reply_or_edit_message(
        update=update,
        context=context,
        text=message_1,
        reply_markup=None,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

    reply_or_edit_message(
        update=update,
        context=context,
        text=message_2,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.CAMPS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        parse_mode='HTML',
        disable_web_page_preview=True,
        force_new_message=True
    )


def camps_stop(update, context):
    """
    Return to top-level menu
    """

    on_top(
        update=update,
        context=context,
        force_new_message=True
    )


def timetable_start(update, context):
    """
    Show current activities
    """

    from_ts = dt.datetime.now(
        tz=timezone
    ).replace(
        tzinfo=None
    ).isoformat(
        timespec='microseconds'
    ) + 'Z'
    
    to_ts = (
        dt.datetime.now(
            tz=timezone
        ).replace(
            tzinfo=None
        ) + dt.timedelta(hours=TIMETABLE_PERIOD_HOURS)
    ).isoformat(
        timespec='microseconds'
    ) + 'Z'

    rows = ydb_client.get_timetable(
        from_ts=from_ts,
        to_ts=to_ts
    )

    message = ''
    last_camp = None

    for row in rows:
        start = getattr(row, ydb_client.start_column)
        end = getattr(row, ydb_client.end_column)
        camp = getattr(row, ydb_client.camp_column)
        description = getattr(row, ydb_client.description_column)
        link = getattr(row, ydb_client.link_column)

        if last_camp == camp:
            message += (
                f'\n<b>{dt.datetime.fromtimestamp(start // 10**6).strftime("%H:%M")}</b>—'
                f'<b>{dt.datetime.fromtimestamp(end // 10**6).strftime("%H:%M")}</b>: '
                f'{description}'
            )
        
        else:
            message += (
                f'\n\n<a href="{link}">{camp}</a>:\n'
                f'<b>{dt.datetime.fromtimestamp(start // 10**6).strftime("%H:%M")}</b>—'
                f'<b>{dt.datetime.fromtimestamp(end // 10**6).strftime("%H:%M")}</b>: '
                f'{description}'
            )
        
        last_camp = camp
    
    if message == '':
        message = 'В расписании в ближайшее время ничего нет, но в реальности наверняка что-то происходит!'
    
    else:
        message = (
            'По расписанию на Холодке работает только столовая, но примерно в '
            f'ближайшие {TIMETABLE_PERIOD_HOURS} часа можно ожидать следующего (полное расписание '
            'лагерей по ссылкам):' + message
        )
    
    if len(message) <= constants.MAX_MESSAGE_LENGTH:
        reply_or_edit_message(
            update=update,
            context=context,
            text=message,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text='Назад',
                            callback_data=callbacks.TIMETABLE_STOP
                        )
                    ]
                ],
                resize_keyboard=True
            ),
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    
    else:
        message_1 = message[:message.find('\n\n', len(message) // 2)]
        message_2 = message[message.find('\n\n', len(message) // 2):].strip()

        reply_or_edit_message(
            update=update,
            context=context,
            text=message_1,
            reply_markup=None,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

        reply_or_edit_message(
            update=update,
            context=context,
            text=message_2,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text='Назад',
                            callback_data=callbacks.TIMETABLE_STOP
                        )
                    ]
                ],
                resize_keyboard=True
            ),
            parse_mode='HTML',
            disable_web_page_preview=True,
            force_new_message=True
        )


def timetable_stop(update, context):
    """
    Return to top-level menu
    """

    on_top(
        update=update,
        context=context,
        force_new_message=True
    )


def map_start(update, context):
    """
    Send one map as a document and another one as a link
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=None,
        media=InputMediaDocument(
            media=os.getenv('MAP_DOCUMENT_ID'),
            caption=(
                'Карту Холодка можно посмотреть сразу в двух вариантах: '
                f'интерактивную на <a href="{os.getenv("MAP_LINK")}">Google Maps</a> или '
                'статичную, но очень красивую в виде вот такого изображения ↑\n\n'
                'Чтобы построить маршрут на карте, откройте ссылку на Google Maps, '
                'затем нажмите слева вверху символ меню, выберете в списке нужный вам кэмп '
                'и наконец вверху страницы справа от названия кэмпа нажмите на стрелку вправо, '
                'тогда Google построит маршрут от вашего местоположения до этого места'
            ),
            parse_mode='HTML'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.MAP_STOP
                    )
                ]
            ],
            resize_keyboard=True
        )
    )


def map_stop(update, context):
    """
    Return to top-level menu
    """

    on_top(update, context)


def shuttle_start(update, context):
    """
    Send link to shuttle locations
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Текущую геолокацию шаттла между «Дружбой» и «Зеленым городком» можно найти в '
            f'<a href="{os.getenv("SHUTTLE_LINK")}">данном сообщении</a> канала «Холодок: Объявления»'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.SHUTTLE_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        parse_mode='HTML'
    )


def shuttle_stop(update, context):
    """
    Return to top-level menu
    """

    on_top(update, context)


def shelter_start(update, context):
    """
    Show a link to the radio
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            f'Послушать радио <a href="https://telegra.ph/Piratskoe-radio-SHalashFM-02-19">'
            f'лагеря ШалашFM</a> можно на волне 93.0 FM или по следующей ссылке: {os.getenv("SHELTER_LINK")}'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.SHELTER_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        parse_mode='HTML',
        disable_web_page_preview=True
    )


def shelter_stop(update, context):
    """
    Return to top-level menu
    """

    on_top(update, context)


def mortuary_start(update, context):
    """
    Propose to show death memes to user
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Лагерь «<a href="https://telegra.ph/PogrebalNYA-i-Dushnyj-bar-02-19">ПогребальНЯ и Душный бар</a>» '
            '(«Дружба», корпус 2) предлагает вам подборку «<i>смертельных мемов</i>» — не плакать же по этому поводу!'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Показать мем',
                        callback_data=callbacks.MORTUARY_SHOW_MEME
                    ),
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.MORTUARY_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

    return states.MORTUARY_CHOOSE_ACTION


def mortuary_show_meme(update, context):
    """
    Show a random unseen death meme
    """
    
    # New meme
    meme = None

    # Memes user already has seen
    seen = context.user_data.get('seen_memes', [])

    # Leftover memes
    unseen = list(filter(lambda meme: meme[1] not in seen, memes_data))

    if unseen:
        # Choose random meme
        meme = random.choice(unseen)
        
    else:
        # Send final message and exit
        reply_or_edit_message(
            update=update,
            context=context,
            text=(
                'Если вы еще живы, приходите в '
                '«<a href="https://telegra.ph/PogrebalNYA-i-Dushnyj-bar-02-19">Погребальню</a>», '
                'или можете посмотреть все мемы еще раз'
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text='Начать заново',
                            callback_data=callbacks.MORTUARY_START_OVER
                        ),
                        InlineKeyboardButton(
                            text='Назад',
                            callback_data=callbacks.MORTUARY_STOP
                        )
                    ]
                ],
                resize_keyboard=True
            ),
            parse_mode='HTML',
            disable_web_page_preview=True
        )

        return states.MORTUARY_CHOOSE_ACTION
    
    # Send meme depending on its type
    reply_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text='Показать мем',
                    callback_data=callbacks.MORTUARY_SHOW_MEME
                ),
                InlineKeyboardButton(
                    text='Назад',
                    callback_data=callbacks.MORTUARY_STOP
                )
            ]
        ],
        resize_keyboard=True
    )

    if meme[0] == types.ANIMATION:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaAnimation(
                media=meme[1],
                caption=meme[2]
            ),
            reply_markup=reply_markup
        )
    
    elif meme[0] == types.PHOTO:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaPhoto(
                media=meme[1],
                caption=meme[2]
            ),
            reply_markup=reply_markup
        )
    
    elif meme[0] == types.VIDEO:
        reply_or_edit_message(
            update=update,
            context=context,
            media=InputMediaVideo(
                media=meme[1],
                caption=meme[2]
            ),
            reply_markup=reply_markup
        )
    
    else:
        raise ValueError(f'Unknown meme type = {meme[0]}')

    # Check this meme has been seen
    seen.append(meme[1])
    context.user_data['seen_memes'] = seen

    return states.MORTUARY_CHOOSE_ACTION


def mortuary_start_over(update, context):
    """
    Clear the list of memes the user has seen and start again
    """

    context.user_data['seen_memes'] = []

    return mortuary_show_meme(update, context)


def mortuary_stop(update, context):
    """
    End conversation and return to top-level menu
    """

    on_top(update, context)

    return states.END


def principles_start(update, context):
    """
    Send description of Burning Man principles and menu with paginated list of all of them
    """

    paginator = InlineKeyboardPaginator(
        page_count=len(principles_data),
        current_page=None,
        current_page_format=False,
        data_pattern=callbacks.PRINCIPLES_PAGE + '#{page}'
    )

    paginator.add_after(
        InlineKeyboardButton(
            text='Назад',
            callback_data=callbacks.PRINCIPLES_STOP
        )
    )

    reply_or_edit_message(
        update=update,
        context=context,
        text=principles_description,
        reply_markup=paginator.markup,
        parse_mode='HTML'
    )

    return states.PRINCIPLES_CHOOSE_ACTION


def principles_page(update, context):
    """
    Show a corresponding Burning Man principle
    """

    page = int(update.callback_query.data.split('#')[1])

    paginator = InlineKeyboardPaginator(
        page_count=len(principles_data),
        current_page=page,
        data_pattern=callbacks.PRINCIPLES_PAGE + '#{page}'
    )

    paginator.add_after(
        InlineKeyboardButton(
            text='Назад',
            callback_data=callbacks.PRINCIPLES_STOP
        )
    )

    reply_or_edit_message(
        update=update,
        context=context,
        text=principles_data[page - 1],
        reply_markup=paginator.markup,
        parse_mode='HTML'
    )

    return states.PRINCIPLES_CHOOSE_ACTION


def principles_stop(update, context):
    """
    End conversation and return to top-level menu
    """

    on_top(update, context)

    return states.END


def sos_start(update, context):
    """
    Show a phone number for emergency communication
    """

    reply_or_edit_message(
        update=update,
        context=context,
        text=(
            'Телефон для экстренной связи со штабом: ... .\n\n'
            'Это не инфоцентр, а номер на случай действительно экстренной ситуации. Во всех остальных случаях просьба '
            'передавать информацию через чаты, рации или с помощью лагеря '
            '«<a href="https://telegra.ph/Pochtovaya-sluzhba-Vezdehody-02-19">Вездеходы</a>» 📬'
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Назад',
                        callback_data=callbacks.SOS_STOP
                    )
                ]
            ],
            resize_keyboard=True
        ),
        parse_mode='HTML',
        disable_web_page_preview=True
    )


def sos_stop(update, context):
    """
    Return to top-level menu
    """

    on_top(update, context)


def on_unknown(update, context):
    """
    Send a confusing smile when we can't find a suitable handler
    """
    
    on_top(
        update=update,
        context=context,
        text=(
            'Сорри, не понял тебя ¯\_(ツ)_/¯\n\n'
            'Давай попробуем еще раз. Что хочешь сделать?'
        )
    )

    # Remove post channel data if present
    context.user_data.pop('post_channel_message', None)
    context.user_data.pop('post_channel_message_type', None)
    context.user_data.pop('post_channel_file_id', None)
    context.user_data.pop('post_channel_full_message', None)
    context.user_data.pop('post_channel_public_footer', None)
    context.user_data.pop('post_channel_private_footer', None)
    context.user_data.pop('post_channel_footer_max_length', None)

    # In case it was a conversation, save the error to end all of them
    context.user_data['UNKNOWN'] = True


def on_every(update, context):
    """
    Increment user's bot usage data after processing an update
    """

    # TO DO: Check for missing user_id (channel and pool events)
    ydb_client.update_usage(
        user_id=update.effective_user.id
    )

    # Log action
    if update.callback_query:
        action = update.callback_query.data
    
    elif (
        update.effective_message and \
        update.effective_message.text and \
        update.effective_message.text.startswith('/')
    ):
        action = update.effective_message.text
    
    elif update.effective_message:
        action = 'message'
    
    else:
        action = 'other'

    logger.info(f'Processed action: {action}')


def on_error(update, context):
    """
    Log the error, clear data and notify the developer and the user by Telegram messages
    """

    logger.error(
        msg='Exception while handling an update:',
        exc_info=context.error
    )

    # Convert error messages from lists to to strings
    exception_msg = ''.join(traceback.format_exception_only(None, context.error))

    traceback_msg = ''.join(traceback.format_exception(None, context.error, context.error.__traceback__))

    update_str = update.to_dict() if isinstance(update, Update) else str(update)

    # Build a message to the developer with all relevant information
    # and clip it to fit the error with closing </pre> tag in one message
    message = (
        f'An exception was raised while handling an update:\n\n'
        f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}\n\n'
        f'context.chat_data = {html.escape(str(context.chat_data))}\n\n'
        f'context.user_data = {html.escape(str(context.user_data))}\n\n'
        f'exception = {html.escape(exception_msg)}\n\n'
        f'{html.escape(traceback_msg)}'
    )[:constants.MAX_MESSAGE_LENGTH - 6] + '</pre>'

    # Send message to the developer
    notify_developer(
        message=message,
        context=context
    )

    # Send message to the user
    update.effective_message.reply_text(
        text='Упс, что-то пошло не так, но админ уже спешит на помощь! 👨‍🦽'
    )

    # Save the error info to clear user data and conversations
    # on updating persistence
    context.user_data['ERROR'] = True


def on_media(update, context):

    # Animation should be checked before document
    if update.message.animation is not None:
        message_type = types.ANIMATION
        message_file_id = update.message.animation.file_id

    elif update.message.audio is not None:
        message_type = types.AUDIO
        message_file_id = update.message.audio.file_id
    
    elif update.message.document is not None:
        message_type = types.DOCUMENT
        message_file_id = update.message.document.file_id

    # Photo attribute is a possibly empty list
    elif update.message.photo:
        message_type = types.PHOTO
        # Photo is a list of telegram.PhotoSize with available sizes of the photo
        message_file_id = update.message.photo[0].file_id

    elif update.message.video is not None:
        message_type = types.VIDEO
        message_file_id = update.message.video.file_id
    
    else:
        return on_unknown(update, context)

    on_top(
        update=update,
        context=context,
        text=(
            f'file type: {message_type}, file id: {message_file_id}'
        )
    )


def add_handlers(dispatcher):
    """
    Add all event handlers to the corresponding dispatcher
    """

    # GENERAL
    dispatcher.add_handler(
        CommandHandler(
            command='start',
            callback=on_start
        )
    )
    
    dispatcher.add_handler(
        CommandHandler(
            command='help',
            callback=on_help
        )
    )

    # POST_CHANNEL
    dispatcher.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler(
                    command='publish',
                    callback=post_channel_start
                ),
                CallbackQueryHandler(
                    pattern=f'^{callbacks.POST_CHANNEL_START}$',
                    callback=post_channel_start
                )
            ],
            states={
                states.POST_CHANNEL_GET_MESSAGE: [
                    MessageHandler(
                        filters=(
                            # Text or media with captions without groups
                            (
                                (Filters.text & (~Filters.command)) |
                                Filters.animation |
                                Filters.audio |
                                Filters.document |
                                Filters.photo |
                                Filters.video
                            ) & (
                                ~fiter_media_group
                            )
                        ),
                        callback=post_channel_message
                    )
                ],
                states.POST_CHANNEL_GET_PRIVACY: [
                    CallbackQueryHandler(
                        pattern=(
                            f'^{callbacks.POST_CHANNEL_PUBLIC}$'
                            '|'
                            f'^{callbacks.POST_CHANNEL_PRIVATE}$'
                        ),
                        callback=post_channel_privacy
                    )
                ],
                states.POST_CHANNEL_GET_SENDING_CONFIRMATION: [
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.POST_CHANNEL_CONFIRM_SENDING}$',
                        callback=post_channel_confirm_sending
                    )
                ],
            },
            fallbacks=[
                CallbackQueryHandler(
                    pattern=f'^{callbacks.POST_CHANNEL_STOP}$',
                    callback=post_channel_stop
                )
            ],
            allow_reentry=True,
            per_user=True,
            per_chat=False,
            per_message=False,
            name='post_channel_conv',
            persistent=True,
        )
    )

    # MEETINGS
    dispatcher.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler(
                    command='meetings',
                    callback=meetings_start
                ),
                CallbackQueryHandler(
                    pattern=f'^{callbacks.MEETINGS_START}$',
                    callback=meetings_start
                )
            ],
            states={
                states.MEETINGS_GET_NAME: [
                    MessageHandler(
                        filters=(
                            Filters.text & (~Filters.command)
                        ),
                        callback=meetings_name
                    )
                ],
                states.MEETINGS_GET_PHOTO:  [
                    MessageHandler(
                        filters=(
                            (
                                Filters.photo |
                                Filters.video
                            ) & (
                                ~fiter_media_group
                            )
                        ),
                        callback=meetings_photo
                    )
                ],
                states.MEETINGS_GET_BIO: [
                    MessageHandler(
                        filters=(
                            Filters.text & (~Filters.command)
                        ),
                        callback=meetings_bio
                    )
                ],
                states.MEETINGS_GET_PARTICIPATION_CONFIRMATION: [
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_CONFIRM_PARTICIPATION}$',
                        callback=meetings_confirm_participation
                    )
                ],
                states.MEETINGS_CHOOSE_ACTION: [
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_SHOW_PEOPLE}$',
                        callback=meetings_show_people
                    ),
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_SHOW_LIKES}$',
                        callback=meetings_show_likes
                    ),
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_CHANGE}$',
                        callback=meetings_change
                    ),
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_REMOVE}$',
                        callback=meetings_remove
                    )
                ],
                states.MEETINGS_CHOOSE_PERSON_ACTION: [
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_SHOW_PEOPLE_LEFT}$',
                        callback=meetings_show_people_left
                    ),
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_LIKE}$',
                        callback=meetings_like
                    ),
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_SHOW_PEOPLE_RIGHT}$',
                        callback=meetings_show_people_right
                    )
                ],
                states.MEETINGS_GET_CHANGE_CONFIRMATION: [
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_CONFIRM_CHANGE}$',
                        callback=meetings_confirm_change
                    )
                ],
                states.MEETINGS_GET_REMOVAL_CONFIRMATION: [
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MEETINGS_CONFIRM_REMOVAL}$',
                        callback=meetings_confirm_removal
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    pattern=f'^{callbacks.MEETINGS_STOP}$',
                    callback=meetings_stop
                )
            ],
            allow_reentry=True,
            per_user=True,
            per_chat=False,
            per_message=False,
            name='meetings_conv',
            persistent=True,
        )
    )

    # CAMPS
    dispatcher.add_handler(
        CommandHandler(
            command='camps',
            callback=camps_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.CAMPS_START}$',
            callback=camps_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.CAMPS_STOP}$',
            callback=camps_stop
        )
    )

    # TIMETABLE
    dispatcher.add_handler(
        CommandHandler(
            command='timetable',
            callback=timetable_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.TIMETABLE_START}$',
            callback=timetable_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.TIMETABLE_STOP}$',
            callback=timetable_stop
        )
    )

    # MAP
    dispatcher.add_handler(
        CommandHandler(
            command='map',
            callback=map_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.MAP_START}$',
            callback=map_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.MAP_STOP}$',
            callback=map_stop
        )
    )

    # SHUTTLE
    dispatcher.add_handler(
        CommandHandler(
            command='shuttle',
            callback=shuttle_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.SHUTTLE_START}$',
            callback=shuttle_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.SHUTTLE_STOP}$',
            callback=shuttle_stop
        )
    )

    # SHELTER
    dispatcher.add_handler(
        CommandHandler(
            command='shalashfm',
            callback=shelter_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.SHELTER_START}$',
            callback=shelter_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.SHELTER_STOP}$',
            callback=shelter_stop
        )
    )

    # MORTUARY
    dispatcher.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler(
                    command='memes',
                    callback=mortuary_start
                ),
                CallbackQueryHandler(
                    pattern=f'^{callbacks.MORTUARY_START}$',
                    callback=mortuary_start
                )
            ],
            states={
                states.MORTUARY_CHOOSE_ACTION: [
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MORTUARY_SHOW_MEME}',
                        callback=mortuary_show_meme
                    ),
                    CallbackQueryHandler(
                        pattern=f'^{callbacks.MORTUARY_START_OVER}',
                        callback=mortuary_start_over
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    pattern=f'^{callbacks.MORTUARY_STOP}$',
                    callback=mortuary_stop
                )
            ],
            allow_reentry=True,
            per_user=True,
            per_chat=False,
            per_message=False,
            name='mortuary_conv',
            persistent=True,
        )
    )

    # PRINCIPLES
    dispatcher.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler(
                    command='principles',
                    callback=principles_start
                ),
                CallbackQueryHandler(
                    pattern=f'^{callbacks.PRINCIPLES_START}$',
                    callback=principles_start
                )
            ],
            states={
                states.PRINCIPLES_CHOOSE_ACTION: [
                    CallbackQueryHandler(
                        # Callback starting with pattern
                        pattern=f'^{callbacks.PRINCIPLES_PAGE}',
                        callback=principles_page
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    pattern=f'^{callbacks.PRINCIPLES_STOP}$',
                    callback=principles_stop
                )
            ],
            allow_reentry=True,
            per_user=True,
            per_chat=False,
            per_message=False,
            name='principles_conv',
            persistent=True,
        )
    )

    # SOS
    dispatcher.add_handler(
        CommandHandler(
            command='sos',
            callback=sos_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.SOS_START}$',
            callback=sos_start
        )
    )

    dispatcher.add_handler(
        CallbackQueryHandler(
            pattern=f'^{callbacks.SOS_STOP}$',
            callback=sos_stop
        )
    )

    # OTHER
    dispatcher.add_handler(
        MessageHandler(
            filters=(
                (
                    Filters.caption(['симсалабим'])
                ) & (
                    Filters.animation |
                    Filters.audio |
                    Filters.document |
                    Filters.photo |
                    Filters.video
                ) & (
                    ~fiter_media_group
                )
            ),
            callback=on_media
        )
    )

    dispatcher.add_handler(
        TypeHandler(
            type=Update,
            callback=on_unknown
        )
    )

    dispatcher.add_handler(
        TypeHandler(
            type=Update,
            callback=on_every
        ),
        group=1
    )

    dispatcher.add_error_handler(
        callback=on_error
    )
