import datetime as dt
import json
import re

from bottle import run, request, post, get
import pymongo
from bson import json_util

# Connection to MongoDB
myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Cal = mydb["Calendar"]
Event = mydb["Events"]

# shows all events
@get('/')
def index():
    return json_util.dumps(Event.find())

#shows all calendar
@get('/cal')
def calendar():
    return json_util.dumps(Cal.find())

def get_all_types(request):
    commas = []
    types = []
    for item in re.finditer(',', request):
        commas.append(item.start())
    
    types.append(request[0:commas[0]])
    #add check if - greater than 1 
    for i in range(0, len(commas)-1):
        types.append(request[commas[i]+1: commas[i+1]])
    types.append(request[commas[len(commas)-1]+1:len(request)])
    return types

# shows all events given calendar
@get('/list_cal_event')
def list_event():
    items_ev = []
    temp_type = request.params.get('type')
    
    type = get_all_types(temp_type)
    print(type)
    #Now, type is a list of this form: ['Scuola', 'Work'], so you must make multiple queries (or a single query with an OR operator)

    items = Cal.find({'Type': type}, {'Events': 1})
    res = items[0]['Events']
    for x in res:
        items_ev.append(Event.find({'id': x}, {'title', 'start', 'end'}))
    s = (str) (json_util.dumps(items_ev))
    a = ((s.replace('[', '')).replace(']', ''))
    return "[" + a + "]"


# modify a given event title
@post('/mod_title')
def update_title_events():
    id_event = request.params.get('id')
    title = request.params.get('title')
    myquery = {"ID": id_event}
    newvalues = {"$set": {"Title": title}}
    Event.update_one(myquery, newvalues)
    item = Event.find()
    return json_util.dumps(item)


# delete a specific event
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


# get events given event type
@post('/type_event')
def vis_event_title():
    type = request.params.get('type')
    myquery = {"Type": type}
    item = Event.find(myquery, {'Title', 'ID'})
    return json_util.dumps(item)


def create_query(list_param):
    query = {}
    for i in range(0, len(list_param)):
        query[list_param[i][0]] = list_param[i][1]
    return query


def get_query(request):
    pair = []
    equal_list = []
    dollar_list = []
    for item in re.finditer('&', request):
        dollar_list.append(item.start())

    for item in re.finditer('=', request):
        equal_list.append(item.start())

    pair.append(((request[0:equal_list[0]]), request[equal_list[0] + 1:dollar_list[0]]))
    for i in range(0, len(dollar_list) - 1):
        pair.append((request[dollar_list[i] + 1:equal_list[i + 1]], request[equal_list[i + 1] + 1:dollar_list[i + 1]]))
    pair.append((request[dollar_list[len(dollar_list) - 1] + 1:equal_list[len(dollar_list)]],
                 request[equal_list[len(dollar_list)] + 1:len(request)]))
    return create_query(pair)


# insert new event
# curl --data "id=6&title=Cena Fisic&type=Cena&start=2021-11-10T13:45:00.000Z&end=2021-11-10T13:45:00.000Z&calendar=School" http://0.0.0.0:12345/insert_event
@post('/insert_event')
def insert_event():
    query = get_query(request.body.read().decode('utf-8'))
    print(query)

    #id = request.params.get('id')
    #title = request.params.get('Title')
    # type = request.params.get('type')
    # start = request.params.get('start')
    # end = request.params.get('end')
    # calendar = request.params.get('calendar')
    # start_date = datetime.datetime.strptime(start, "%Y-%m-%dT%H:%M:%S.000Z")
    # end_date = datetime.datetime.strptime(end, "%Y-%m-%dT%H:%M:%S.000Z")
    # myquery = {'id': id, 'Title': title}
    #print(myquery)


    Event.insert_one(query)
    #myquery2 = {'Type': calendar}
    #newvalues = {"$addToSet": {'Events': id}}
    #Cal.update_one(myquery2, newvalues)
    #item = Event.find()


run(host='192.168.188.80', port=12345, debug=True)

