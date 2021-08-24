import pymongo

# Connection to MongoDB
myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Cal = mydb["Calendar"]
Event = mydb["Events"]
Precondition = mydb["Temporal Pre-Condition"]
Admin_Auth = mydb["Admin_Auth"]
Auth = mydb["Authorization"]
User = mydb["User"]
Group = mydb["Group"]
Hier = mydb["Hier"]

def getCal():
    return Cal

def getEvent():
    return Event

def getPrecondition():
    return Precondition

def getAdmin_Auth():
    return Admin_Auth

def getAuth():
    return Auth

def getUser():
    return User

def getGroup():
    return Group

def getHier():
    return Hier