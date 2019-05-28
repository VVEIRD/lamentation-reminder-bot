# -*- coding: utf-8 -*-
## Bot to remind Chatroom about the next rpg event
#
#

import caldav
from datetime import datetime, date, time, timedelta
import sys
import json
import sqlite3
from telegram.ext import Updater
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters
import os
import logging
from threading import Thread
import sys
import re
import random
from emoji import emojize

TELEGRAM_TOKEN = sys.argv[1]
CAL_DAV_URL = sys.argv[2]
USERNAME = sys.argv[3]
PASSWORD = sys.argv[4]
CALENDAR_NAME = sys.argv[5]

print 'Starting Reminder Bot for %s in %s' % (CALENDAR_NAME, CAL_DAV_URL)

botName  = 'LamentationBot'

sqliteDb = botName + '.db'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

conn = sqlite3.connect(sqliteDb)

c = conn.cursor()

# Create table
c.execute('''CREATE TABLE IF NOT EXISTS chatrooms
             (
                chat_id integer
              )''')

c.execute('''CREATE TABLE IF NOT EXISTS chatrooms_informed
             (chat_id integer,
                vEventDate TEXT,
                vEventTime TEXT,
                vEventName TEXT
              )''')


######
## Liste mit den Chats die der Bot angehoert
######

def load_chatrooms():
    conn = sqlite3.connect(sqliteDb)
    c = conn.cursor()
    chatrooms = {}
    for row in c.execute('SELECT chat_id FROM chatrooms'):
        chatrooms[row[0]] = row[0]
    conn.close()
    return chatrooms

# Lade chatrooms wenn die Datei fuer chatrooms existiert

chatrooms = load_chatrooms()

# Wenn keine Location existiert, erzeuge eine leere Liste

if chatrooms == None:
    chatrooms = {}

conn.commit()
conn.close()

client = caldav.DAVClient(CAL_DAV_URL, username=USERNAME, password=PASSWORD)
principal = client.principal()
cal = None
for calendar in principal.calendars():
    print '%s vs %s' % (CALENDAR_NAME, calendar.name)
    if CALENDAR_NAME in calendar.name:
        cal = calendar
        print 'Calendar found: %s' % cal.name


######
## Methoden fuer den Chatbot
######

# Fuehrt ein Query aus, liefert keine Daten zurueck
def execute_query(query, args):
    conn = sqlite3.connect(sqliteDb)
    c = conn.cursor()
    c.execute(query, args)
    conn.commit()
    conn.close()

# Fuert ein Query aus, liefert das Resultat als 2D-Array zurueck
def execute_select(query, args):
    conn = sqlite3.connect(sqliteDb)
    c = conn.cursor()
    result = []
    for row in c.execute(query, args):
        result.append(row)
    conn.close()
    return result

# Fuegt einen neuen Gruppenchat hinzu, in dem der Bot hinzugefuegt wurde
def add_chatroom(chat_id):
    if chat_id not in chatrooms:
        chatrooms[chat_id] = chat_id
        print 'New chatroom: ' + str(chat_id)
        execute_query('INSERT INTO chatrooms (chat_id) VALUES (?)',  [chat_id])

# Entfernt alle Daten ueber einen Gruppenchat, asu dem der Bot entfernt wurde
def remove_chatroom(chat_id):
    if chat_id in chatrooms:
        print 'Removed from Chat: ' + str(chat_id)
        chatrooms.pop(chat_id, None)
        execute_query('DELETE FROM chatrooms WHERE chat_id = ?', [chat_id])
        execute_query('DELETE FROM chatrooms_informed WHERE chat_id = ?', [chat_id])
        print 'Removed from chatroom: %s' % chat_id

# Event handler wenn der Bot einem Gruppenchat hinzugefuegt wird
def new_member(update, context):
    for member in update.message.new_chat_members:
        print(member)
        if member.username == botName:
            add_chatroom(update.message.chat.id)

# Event handler wenn der Bot einem Gruppenchat entfernt wird
def left_member(update, context):
    member = update.message.left_chat_member
    print(member)
    if member.username == botName:
        remove_chatroom(update.message.chat.id)

def channel_already_informed(chat_id, vEventDate, vEventStartTime, vEventName):
    return len(execute_select('SELECT 1 FROM chatrooms_informed WHERE chat_id = ? AND vEventDate = ? AND vEventTime = ? AND vEventName = ?', [chat_id, vEventDate, vEventStartTime, vEventName])) > 0

def show_calendar_name(update, context):
        update.message.reply_text(u'Kalender %s wird verwendet' % CALENDAR_NAME)

def send_event(chat_id, context, startDate, event):
    e = event.instance.vevent
    vEventName = e.summary.value
    vEventStatus = e.status.value
    vEventLocation = e.location.value
    vEventTime = startDate.date().strftime('%Y%m%d') + 'T' + e.dtstart.value.strftime('%H%M') + '00Z'
    vEvent = '''BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:%s@%s/%s@%s
SUMMARY:%s
DTSTART:%s
DURATION:PT4H
END:VEVENT
END:VCALENDAR''' % (botName, CALENDAR_NAME.replace(' ', ''), vEventName.replace(' ', ''), vEventTime, vEventName, vEventTime)
    vEvFile = open(vEventName + '.vcs','w')
    vEvFile.write(vEvent)
    vEvFile.close()
    context.bot.send_document(chat_id=chat_id, document=open(vEventName + '.vcs', 'rb'))

def check_for_events(context):
    for chat_id in chatrooms:
        startDate = datetime.combine(datetime.today() + timedelta(2), time(0, 0))
        endDate = datetime.combine(datetime.today() + timedelta(2), time(23, 59))
        for event in cal.date_search(startDate, endDate):
            event.load()
            e = event.instance.vevent
            vEventStartTime = e.dtstart.value.strftime("%H:%M")
            vEventDate = startDate.date().strftime("%d.%m.%Y")
            vEventName = e.summary.value
            vEventLocation = e.location.value
            already_informed = channel_already_informed(chat_id, vEventDate, vEventStartTime, vEventName)
            print 'Event %s, am %s um %s, bereits informiert %s' % (vEventName, vEventDate, vEventStartTime, already_informed)
            if not already_informed:
                message = '''%s 
findet am %s um %s
%s statt.''' % (vEventName, vEventDate, vEventStartTime, vEventLocation)
                # Tippe 1 in den Chat wenn du teilnimmst.
                context.bot.send_message(chat_id=chat_id, text=message)
                send_event(chat_id, context, startDate, event)
                execute_query('INSERT INTO chatrooms_informed (chat_id, vEventDate, vEventTime, vEventName) VALUES (?, ?, ?, ?)', [chat_id, vEventDate, vEventStartTime, vEventName])

def roll_dice(diceType, times):
    diceResultList = []
    for a in range(0, times):
        diceResultList.append(random.randint(1,diceType))
    return diceResultList

def dice(update, context):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    msg = update.message.text.strip() if update.message.text <> None else ''
    # Regex Suchen fuer wuerfelwuerfe
    dx_w_mod = '[D|d|W|w](?P<Dice>\d+)\s*(?P<AddSub>[\+|\-])\s*(?P<Modifier>\d+)'
    dx_w_mod_multi = '(?P<Multi>\d+)[D|d|W|w](?P<Dice>\d+)\s*(?P<AddSub>[\+|\-])\s*(?P<Modifier>\d+)'
    dx_no_mod = '[D|d|W|w](?P<Dice>\d+)'
    dx_no_mod_multi = '(?P<Multi>\d+)[D|d|W|w](?P<Dice>\d+)'
    match_dx_w_mod = re.search(dx_w_mod, msg)
    match_dx_w_mod_multi = re.search(dx_w_mod_multi, msg)
    match_dx_no_mod = re.search(dx_no_mod, msg)
    match_dx_no_mod_multi = re.search(dx_no_mod_multi, msg)
    multi = 1
    if match_dx_w_mod_multi and match_dx_w_mod:
        multi = int(match_dx_w_mod_multi.group('Multi'))
    elif match_dx_no_mod and match_dx_no_mod_multi:
        multi = int(match_dx_no_mod_multi.group('Multi'))
    if multi > 100:
        update.message.reply_text('😫 Zu viele Würfel!')
        return
    result = 1
    isNaturalOne = False
    isNatural20 = False
    diceListString = ""
    if match_dx_w_mod:
        dice = int(match_dx_w_mod.group('Dice'))
        addSub = match_dx_w_mod.group('AddSub')
        modifier = int(match_dx_w_mod.group('Modifier'))
        diceResultList = roll_dice(dice, multi)
        diceResult = sum(diceResultList)
        diceListString = "(" + ', '.join(str(x) for x in diceResultList) + ")" + addSub + str(modifier)
        isNaturalOne = diceResult == 1
        isNatural20 = diceResult == 20
        result = diceResult + (modifier if addSub == '+' else -modifier)
        result = result if result > 0 else 1
    elif match_dx_no_mod:
        dice = int(match_dx_no_mod.group('Dice'))
        diceResultList = roll_dice(dice, multi)
        diceResult = sum(diceResultList)
        diceListString = "(" + ', '.join(str(x) for x in diceResultList) + ")"
        isNaturalOne = diceResult == 1
        isNatural20 = diceResult == 20
        result = diceResult
    if match_dx_w_mod or match_dx_no_mod:
        text = u'Ergebnis: %s; Einzeln: %s' % (result, diceListString)
        if isNaturalOne:
            text = u'Oh nein! Eine natürliche 1! (Würfelergebnis: %s; Einzeln: %s)' % (result, diceListString)
        elif isNatural20:
            text = u'Juhu! Eine natürliche 20! (Würfelergebnis: %s; Einzeln: %s)' % (result, diceListString)
        update.message.reply_text(text)


######
## Bot Stuff. Init, Mappen der handler/methoden
######

updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher
jobqueue = updater.job_queue


# Job jeden Tag
job_daily = jobqueue.run_daily(check_for_events, time(8, 0))

# Hilfetext anzeigen
cal_handler = CommandHandler('cal', show_calendar_name)
dispatcher.add_handler(cal_handler)

# Job jede Minute for testing
# job_minute = jobqueue.run_repeating(check_for_events, interval=600, first=0)

# Eventhandler, wenn der Bot einem Chat hinzugefuegt wird
dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, new_member))

#  Eventhandler, wenn der Bot aus einem Chat entfernt wird
dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, left_member))


dispatcher.add_handler(MessageHandler(Filters.group, dice))

updater.start_polling()


updater.idle()
