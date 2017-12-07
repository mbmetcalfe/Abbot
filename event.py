import json
from collections import namedtuple
from pathlib import Path

class Event(object):
    """This class holds the event information and the participants for the event."""
    def __init__(self, name, maxParticipants=None):
        """Initialize the Event object."""
        self.name = name
        self.maxParticipants = maxParticipants
        self.participants = {}
    
    def save(self):
        """Save the Event to a file, in JSON format."""
        file = Path("config/event_{0}.json".format(self.name))
        try:
            file.write_text(self.toJSON())
        except Exception as err:
            raise(err)
        
    def load(self):
        file = Path("config/event_{0}.json".format(self.name))
        with open(file) as json_data:
            d = json.load(json_data)
            self.__dict__ = d
            print(d)

    def status(self):
        print("Event '{0}'; {1} of {2} Participants.".format(
            self.name,
            len(self.participants),
            self.maxParticipants))
        for key, value in self.participants.items():
            value.status()

    def addParticipant(self, participant):
        """Add a participant to the event.  If the max number of participants has been reached, show an error.
           Raises a ValueError exception if an attemp is made to add too many participants."""
        if len(self.participants) < self.maxParticipants:
            self.participants[participant.discordId] = participant
        else:
            raise ValueError('Max number of participants has been reached')
            
    def getParticpants(self):
        """Get the particpants for the event."""
        return participants
        
    def getParticipant(self, discordId):
        """Get a participant with the given discord id.  Returns None if not in the list of participants."""
        if discordId in participants:
            return participants[discordId]
        else:
            return None

    @classmethod
    def from_json(cls, json_str):
        json_dict = json.loads(json_str)
        return cls(**json_dict)

    def fromJSON(self, fileName):
        with open(fileName) as json_data:
            self.__dict__ = json.load(json_data)

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)
    
    def loadObj(self, _object):
        self.name = _object.name
        self.maxParticipants = _object.maxParticipants
        self.participants = dict(_object.participants)
        
class EventParticipant(object):
    """This class holds information pertaining to a participant of an event."""
    def __init__(self, discordId):
        """Initialize the EventParticipant object."""
        self.discordId = discordId
        self.address = None
        self.giftee = None
        self.size = None
    
    def status(self):
        print("\nDiscord Id: {3}\nAddress: {0}\nSize: {1}\nGiftee: {2}".format(
                self.address if self.address != None else "N/A",
                self.size if self.size != None else "N/A",
                self.giftee if self.giftee != None else "Not yet assigned.",
                self.discordId)
            )

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)

def jsonDefault(object):
    """The default JSON object."""
    return object.__dict__

def EventToJSON(_object):
    """Return the JSON representation of the object."""
    return json.dumps(_object, default=jsonDefault)

def JSONtoObject(fileName):
    """Load a JSON file into an object."""
    # TODO: ensure file exists first!!
    
    with open(fileName) as json_data:
        d = json.load(json_data)
        
        return d
        #return json.loads(d, object_hook=_json_object_hook)

def _json_object_hook(d): return namedtuple('X', d.keys())(*d.values())
def json2obj(data): return json.loads(data, object_hook=_json_object_hook)