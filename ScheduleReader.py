
class ScheduleReader:

    def __init__(self):
        self.operators = {'':0}
        self.schedule = [[[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]],[[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]],
                         [[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]],[[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]],
                         [[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]],[[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]],[[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]]]


    def getDiscordId(self, name):
        #names is a string list of all UMBC usernames of everyone on observing shifts
        #index 0 is monday ES1, 1 is monday ES2, 2 is monday MS1
        #if an entry in names == '0' there is no one assigned to a shift
        ids = 0
        index = 0
        while(index < 6):
            ids[index] = int(self.operators[name])
            index += 1
        return ids

    def changeSchedule(self,command):
        words = command.split()
        if(len(self.operators) == 1):
            self.readOperatorFile()

        if((len(words)) != 5):
            return("Command not formatted properly (ex: skybot schedule mon ES1 broslin1)")

        #words = [0"skybot", 1"schedule", 2"Mon", 3"ES1", 4"broslin1"]
        words[2] = words[2].lower()
        day = 10
        if (words[2] == "mon" or words[2] == "monday"):
            day = 0
        if (words[2] == "tue" or words[2] == "tuesday"):
            day = 1
        if (words[2] == "wed" or words[2] == "wednesday"):
            day = 2
        if (words[2] == "thu" or words[2] == "thursday"):
            day = 3
        if (words[2] == "fri" or words[2] == "friday"):
            day = 4
        if (words[2] == "sat" or words[2] == "saturday"):
            day = 5
        if (words[2] == "sun" or words[2] == "sunday"):
            day = 6
        if day == 10:
            return ("Day inputted incorrectly, please input it as first 3 letters of the day (ex:thu for thursday)")
        
        shift = 10
        words[3] = words[3].lower()
        if (words[3] == "es1"):
            shift = 1
        if (words[3] == "es2"):
            shift = 2
        if (words[3] == "ms1"):
            shift = 3
        if (words[3] == "ms2"):
            shift = 4
        if (words[3] == "gs1"):
            shift = 5
        if (words[3] == "gs2"):
            shift = 6

        if shift == 10:
            return ("Shift inputted incorrectly, please input correctly (ex:ES1)")
        
        if words[4] in self.operators:
            opId = self.operators[words[4]]
        else:
            return ("Operator UMBC ID does not exist")

        oldFile = open("schedule.csv",'r')
        oldSched = oldFile.readlines()
        oldFile.close()
        line = 0
        rewrite = ((day * 7) + shift)
        newFile = open("schedule.csv",'w')
        while(line < len(oldSched)):
            if(line == rewrite):
                newFile.write(words[4] + ',' + opId + "\n")
            else:
                newFile.write(oldSched[line])
            line += 1
        newFile.close()
        return ("Shift successfully set")
        
        

        


    def readOperatorFile(self):
        #operators.csv and turns all UMBC usernames into a dict with corresponding ID
        idFile = open("operators.csv", 'r')
        lines = idFile.read().splitlines()
        index = 0
        while(index < len(lines)):
            operator = lines[index].split(',')
            self.operators[operator[0]] = operator[1]
            index += 1
        idFile.close()

    
    def readScheduleFile(self):
        file = open("schedule.csv",'r')
        lines = file.read().splitlines()
        index = 0
        day = -1
        for line in lines:
            operator = line.split(',')
            if(len(operator) == 1):
                day +=1
                index = 0
            else:
                self.schedule[day][index][0] = operator[0]
                self.schedule[day][index][1] = operator[1]
                index += 1
        file.close()

    def getSchedule(self,day):
        return self.schedule[day]
            
    

if __name__ == "__main__":
    sr = ScheduleReader()
    #sr.readOperatorFile()
    #print(sr.getDiscordIds(["broslin1","jhickey1",'','',"ssilva3","broslin1"]))
    sr.readScheduleFile()
    #print(sr.schedule)
    sr.changeSchedule("skybot schedule mon ES1 broslin1")
