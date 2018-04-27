
from general import GeneralProcess
from message import Message
import time

msg = Message()
print "Hello"
print msg.packObject()

no_generals=3
problemStructure={}
generals=[]
for i in range(no_generals):
    problemStructure["General_%d" % i] = 38000 + i
for gen_name in problemStructure:
    generals.append(GeneralProcess(gen_name, problemStructure))

for gen in generals:
    gen.start()
time.sleep(10)
for gen in generals:
    gen.do_run=False

for gen in generals:
    gen.join()
#proc = GeneralProcess("Hello")
#proc.start()
#time.sleep(10)
#proc.do_run=False
#proc.join()