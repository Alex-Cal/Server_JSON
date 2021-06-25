import datetime

from bottle import run, request, post, get
import pymongo
from bson import json_util

# Connection to MongoDB
myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Cal = mydb["Calendar"]
Event = mydb["Events"]

#shows all events
@get('/')
def index():
    return json_util.dumps(Event.find())

#shows all events given calendar
@post('/list_cal_event')
def list_event():
    items_ev = []
    type = request.params.get('type')
    items = Cal.find({'Type': type}, {'Events': 1})
    res = items[0]['Events']
    for x in res:
        items_ev.append(Event.find({'ID': x}, {'Title'}))
    return json_util.dumps(items_ev)

#modify a given event title
@post('/mod_title')
def update_title_events():
    id_event = request.params.get('id')
    title = request.params.get('title')
    myquery = {"ID": id_event}
    newvalues = {"$set": {"Title": title}}
    Event.update_one(myquery, newvalues)
    item = Event.find()
    return json_util.dumps(item)

#delete a specific event
@post('/delete_event')
def delete_event():
    id_event = request.params.get('id')
    calendar = request.params.get('cal')
    myquery = {"ID": id_event}
    Event.delete_one(myquery)
    query = {"Type": calendar}
    Cal.update_one(query, {"$pull": {'Events': id_event}})
    item = Event.find()
    return json_util.dumps(item)

#get events given event type
@post('/type_event')
def vis_event_title():
    type = request.params.get('type')
    myquery = {"Type": type}
    item = Event.find(myquery, {'Title', 'ID'})
    return json_util.dumps(item)

#insert new event
#curl --data "id=6&title=Cena Fisic&type=Cena&start=2021-11-10T13:45:00.000Z&end=2021-11-10T13:45:00.000Z&calendar=School" http://0.0.0.0:12345/insert_event
@post('/insert_event')
def insert_event():
    id = request.params.get('id')
    title = request.params.get('title')
    type = request.params.get('type')
    start = request.params.get('start')
    end = request.params.get('end')
    calendar = request.params.get('calendar')
    start_date = datetime.datetime.strptime(start, "%Y-%m-%dT%H:%M:%S.000Z")
    end_date = datetime.datetime.strptime(end, "%Y-%m-%dT%H:%M:%S.000Z")
    myquery = {'ID': id, 'Title': title, 'Type': type, 'Start': start_date, 'End': end_date}
    Event.insert_one(myquery)
    myquery2 = {'Type': calendar}
    newvalues = {"$addToSet": {'Events': id}}
    Cal.update_one(myquery2, newvalues)
    item = Event.find()
    return json_util.dumps(item)


run(host='0.0.0.0', port=12345, debug=True)
