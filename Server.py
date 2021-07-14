import time
import json
import re
from datetime import datetime

from bottle import run, request, post, get
import pymongo
from bson import json_util

# Connection to MongoDB
myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Cal = mydb["Calendar"]
Event = mydb["Events"]
Precondition = mydb["Temporal Pre-Condition"]
Auth = mydb["Authorization"]
User = mydb["User"]
Group = mydb["Group"]


# shows all events
@get('/')
def index():
    return json_util.dumps(Event.find())


# shows all calendar
@get('/cal')
def calendar():
    return json_util.dumps(Cal.find())


def get_all_types(request):
    commas = []
    types = []
    for item in re.finditer(',', request):
        commas.append(item.start())

    if len(commas) == 0:
        return request
    types.append(request[0:commas[0]])
    # add check if - greater than 1
    for i in range(0, len(commas) - 1):
        types.append(request[commas[i] + 1: commas[i + 1]])
    types.append(request[commas[len(commas) - 1] + 1:len(request)])
    return types


# shows all events given calendar
@get('/list_cal_event_multiple')
def list_event():
    items_ev = []
    res = []
    s = []
    a = []
    temp_type = request.params.get('type')

    type = get_all_types(temp_type)
    print(type)
    # Now, type is a list of this form: ['Scuola', 'Work'], so you must make multiple queries (or a single query with an OR operator)

    for i in type:
        items = Cal.find({'Type': i}, {'Events': 1})
        print(i)
        res.append(items[0]['Events'])
    for x in res:
        for y in x:
            items_ev.append(Event.find({'id': y}, {'title', 'start', 'end', 'color', 'allDay'}))
    for i in items_ev:
        s.append(str(json_util.dumps(i)))
    print(s)
    return (str(s).replace("'[", '')).replace("]'", '')


# list one type event
@get('/list_cal_event')
def list_one_type_event():
    items_ev = []
    type = request.params.get('type')
    items = Cal.find({'Type': type}, {'Events': 1})
    res = items[0]['Events']
    for x in res:
        items_ev.append(Event.find({'id': x}, {'title', 'start', 'end', 'color', 'allDay'}))
    s = (str)(json_util.dumps(items_ev))
    a = ((s.replace('[', '')).replace(']', ''))
    return "[" + a + "]"


# modify a given event title
@post('/mod_title')
def update_title_events():
    query = get_query(request.body.read().decode('utf-8'))
    myquery = {"id": query['id']}
    newvalues = {"$set": {"title": query['title']}}
    Event.update_one(myquery, newvalues)
    item = Event.find()
    return json_util.dumps(item)


# delete a specific event
@post('/delete_event')
def delete_event():
    query = get_query(request.body.read().decode('utf-8'))
    myquery = {"id": query['id']}
    Event.delete_one(myquery)
    new_query = {"Type": query['calendar']}
    Cal.update_one(new_query, {"$pull": {'Events': query['id']}})
    item = Event.find()
    return json_util.dumps(item)


def crate_query(list_param):
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
    return crate_query(pair)


# insert new event curl --data "id=6&title=Cena Fisic&type=Cena&start=1627819982&end=1627823582&calendar=School"
# http://0.0.0.0:12345/insert_event
@post('/insert_event')
def insert_event():
    query = get_query(request.body.read().decode('utf-8'))
    Event.insert_one(query)
    myquery = {'Type': query['calendar']}
    newvalues = {"$addToSet": {'Events': query['id']}}
    Cal.update_one(myquery, newvalues)


@post('/precondition')
def insert_precondition():
    query = get_query(request.body.read().decode('utf-8'))
    Precondition.insert_one(query)
    myquery = {'Type': query['calendar']}
    newvalues = {"$addToSet": {'Precondition': query['id']}}
    Cal.update_one(myquery, newvalues)
    myquery2 = {'Name': query['name']}
    newvalues2 = {"$addToSet": {'Precondition': query['id']}}
    print(User.find_one({"Name": query['name']}))
    if (User.find_one({"Name": query['name']})) is None:
        Group.update_one(myquery2, newvalues2)
    else:
        User.update_one(myquery2, newvalues2)


def string_repetition(timeslot):
    minus_position = 0
    for item in re.finditer('-', timeslot):
        minus_position = item.start()
    start_day = timeslot[0:1]
    start_hour = timeslot[2:minus_position]
    end_day = timeslot[minus_position + 1:minus_position + 2]
    end_hour = timeslot[minus_position + 3:len(timeslot)]
    return [start_day, start_hour, end_day, end_hour]


def string_not_repetition(timeslot):
    pass


def evaluate_rep(timeslot):
    [start_day, start_hour, end_day, end_hour] = string_repetition(timeslot)
    result = Event.find({}, {"_id": 1, "start": 1, "end": 1})
    good_event = []
    for item in result:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        start_hour_pre = datetime.strptime(start_hour, "%H:%M").time()
        end_hour_pre = datetime.strptime(end_hour, "%H:%M").time()
        if not (int(datetime.weekday(start)) == int(start_day) or int(datetime.weekday(end)) == int(end_day)):
            good_event.append(item)
        else:
            if datetime.time(end) < start_hour_pre or datetime.time(start) > end_hour_pre:
                good_event.append(item)
    return good_event






@post("/event_vis")
def vis():
    query = get_query(request.body.read().decode('utf-8'))
    if (User.find_one({"Name": query['name']})) is None:
        result = Group.find_one({"Name": query['name']}, {"Precondition": 1, "_id": 0})
        for i in result['Precondition']:
            timeslot = Precondition.find({"id": i, "calendar": query['calendar']},
                                         {"timeslot": 1, "_id": 0, "type_time": 1})
            if timeslot[0]["type_time"] == "repetition":
                res = evaluate_rep(timeslot[0]['timeslot'])
                return res
            else:
                string_not_repetition(timeslot[0]['timeslot'])
                #res = evaluate_not_rep()
                #return res

    else:
        result = User.find_one({"Name": query['name']}, {"Precondition": 1, "_id": 0})
        for i in result['Precondition']:
            timeslot = Precondition.find({"id": i, "calendar": query['calendar']},
                                         {"timeslot": 1, "_id": 0, "type_time": 1})
            if timeslot[0]["type_time"] == "repetition":
                string_repetition(timeslot[0]['timeslot'])

            else:
                string_not_repetition(timeslot[0]['timeslot'])


run(host='0.0.0.0', port=12345, debug=True)
