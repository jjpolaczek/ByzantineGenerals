
import pickle

class Message(object):
    def __init__(self):
        self.hell="FEAFA"
        pass
    def packObject(self):
        return pickle.dumps(self, pickle.HIGHEST_PROTOCOL)