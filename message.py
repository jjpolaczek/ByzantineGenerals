
import pickle

class Message(object):
    def __init__(self, sender, value, path):
        self.sender = sender
        self.value = value
        self.path = path

    def packObject(self):
        return pickle.dumps(self, pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def parseString(str):
        return pickle.loads(str)