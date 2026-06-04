#Weather compiler isn't gonna be really working with the new way data is set up
#it is also a complete mess of code that I can barely understand

#functions
#ccAverage - returns a float of the average ccValue for the chosen amount of days out

import dotenv
import datetime
import math
import os
from htmlParser import get_noaa_forecast, get_clearoutside_forecast, generateCCList, generateTimeList, generateTempList

DST_ACTIVE = os.getenv("DST_ACTIVE", "True").lower() == "true"

class WeatherCompiler:
    def __init__(self):
        dotenv.load_dotenv()
        
        self.tempList = generateTempList()
        self.ccList = generateCCList()
        self.timeList = generateTimeList()
        self.noaa_times, self.noaa_cloud = get_noaa_forecast()
        self.co_times, self.co_cloud = get_clearoutside_forecast()

    # Helper functions for the sunrise calculation
    def calculate_julian_day(self, year, month, day):
        if month <= 2:
            year -= 1
            month += 12
        A = math.floor(year / 100)
        B = 2 - A + math.floor(A / 4)
        return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5

    def solar_coordinates(self, days):
        M = math.radians((357.5291 + 0.98560028 * days) % 360)
        C = math.radians(1.9148 * math.sin(M) + 0.02 * math.sin(2 * M) + 0.0003 * math.sin(3 * M))
        lambda_sun = (M + C + math.radians(102.9372) + math.pi) % (2 * math.pi)
        return lambda_sun

    def calculate_sunrise(self, latitude, longitude, date):
        J2000 = self.calculate_julian_day(2000, 1, 1)
        julian_day = self.calculate_julian_day(date.year, date.month, date.day)
        days = julian_day - J2000
    
        # Solar coordinates
        lambda_sun = self.solar_coordinates(days)
    
        # Solar declination
        delta = math.asin(math.sin(lambda_sun) * math.sin(math.radians(23.44)))
    
        # Hour angle
        latitude_rad = math.radians(latitude)
        hour_angle = math.acos((math.sin(math.radians(-0.83)) - math.sin(latitude_rad) * math.sin(delta)) / (math.cos(latitude_rad) * math.cos(delta)))
    
        # Solar noon
        J_transit = J2000 + days + 0.0053 * math.sin(lambda_sun) - 0.0069 * math.sin(2 * lambda_sun)
    
        # Sunrise time in Julian days
        J_sunrise = J_transit - hour_angle / (2 * math.pi)
    
        return J_sunrise
    
    def calculate_sunset(self, latitude, longitude, date):
        # Calculate the Julian day for a given date
        J2000 = self.calculate_julian_day(2000, 1, 1)
        julian_day = self.calculate_julian_day(date.year, date.month, date.day)
        days = julian_day - J2000

        # Solar coordinates
        lambda_sun = self.solar_coordinates(days)

        # Solar declination
        delta = math.asin(math.sin(lambda_sun) * math.sin(math.radians(23.44)))

        # Hour angle for sunset calculation
        latitude_rad = math.radians(latitude)
        hour_angle = math.acos((math.sin(math.radians(-0.83)) - math.sin(latitude_rad) * math.sin(delta)) / (math.cos(latitude_rad) * math.cos(delta)))

        # Solar noon in Julian days
        J_transit = J2000 + days + 0.0053 * math.sin(lambda_sun) - 0.0069 * math.sin(2 * lambda_sun)

        # Sunset time in Julian days
        J_sunset = J_transit + hour_angle / (2 * math.pi)

        return J_sunset

    def julian_to_datetime(self, julian_day):
        J = julian_day + 0.5
        j = int(J)
        f = J - j
        if j >= 2299161:
            a = int((j - 1867216.25) / 36524.25)
            b = j + 1 + a - int(a / 4)
        else:
            b = j
        c = b + 1524
        d = int((c - 122.1) / 365.25)
        e = int(365.25 * d)
        g = int((c - e) / 30.6001)
        day = c - e + f - int(30.6001 * g)
        if g < 13.5:
            month = g - 1
        else:
            month = g - 13
        if month > 2.5:
            year = d - 4716
        else:
            year = d - 4715
    
        day_fraction = day % 1
        day = int(day)
        hour = int(day_fraction * 24)
        minute = int((day_fraction * 24 - hour) * 60)
        second = int((((day_fraction * 24 - hour) * 60) - minute) * 60)
        
    
        return datetime.datetime(year, month, day, hour, minute, second)
    

    #returns time of sunrise
    def sunriseTime(self, date):
            # Location for Baltimore, MD
        latitude = 39.2904
        longitude = 76.6122

        # Current date
        current_date = date

        # Calculate sunrise time
        julian_sunrise = self.calculate_sunrise(latitude, longitude, current_date)
        sunrise_time = self.julian_to_datetime(julian_sunrise)
        sunrise_time = sunrise_time + datetime.timedelta(hours = -12, days = 1)

        return sunrise_time
    
    def sunsetTime(self, date):
            # Location for Baltimore, MD
        latitude = 39.2904
        longitude = 76.6122

        # Current date
        current_date = date

        # Calculate sunrise time
        julian_sunset = self.calculate_sunset(latitude, longitude, current_date)
        sunset_time = self.julian_to_datetime(julian_sunset)
        sunset_time = sunset_time + datetime.timedelta(hours = 12)

        return sunset_time
    

        
    #returns a booleam array indicating whether hour was included in a 3 hour block where the average cc was below 30
    #day = 1 is tonight, day = 2 is tomorrow, day = 3 is two days from now
    #first index in array indicates whether or not there was at least 4 hours in a row of true
    def ccAverage(self, day = 1):
        # Location for Baltimore, MD

        sunset = self.sunsetTime(datetime.date.today() + datetime.timedelta(days = (day - 1))).hour  #Time to start tracking cc values
        sunrise = self.sunriseTime(datetime.date.today() + datetime.timedelta(days = (day))).hour  #time to end tracking cc values

        range = sunrise + 25 - sunset
        dayTrack = 0 #if doing prediction for other than tonight tracks what day index corresponds to
        startIndex = 0 #index of start of time and cc list
        sum = 0
        index = 0
        tempIndex = 0
        goodHours = [False] * (range + 1)
        #
        #
        while dayTrack < (day - 1):
            startIndex = startIndex + 1
            if int(self.timeList[startIndex]) == 0:
                dayTrack += 1
            
        if(day == 1):
            while(int(self.timeList[startIndex]) < sunset):
                startIndex += 1
        else:
            startIndex = startIndex + sunset  #jumps to 1900 hours on day of prediction
        #adds ccValue to ccAvg until end of night and adds to details string
        while (index + 2 < range):
            while(tempIndex < 3):
                sum += int(self.ccList[startIndex + index + tempIndex])
                tempIndex += 1
            if(sum < 90):
                if(goodHours[index]):
                    goodHours[0] = True
                goodHours[index + 1] = True
                goodHours[index + 2] = True
                goodHours[index + 3] = True
            sum = 0
            tempIndex = 0
            index += 1

        #averages ccValue for night
        return goodHours




    #returns details on Cloud coverage on chosen night as a string with cloud cover data for obs hours
    #day = 1 is tonight, day = 2 is tomorrow, day = 3 is two days from now
    def ccForecast(self, day: int, extended):
        """
        Returns sky coverage from 18:00–05:00 for the given day, but skips hours already past.
        Includes NOAA, Temp, and ClearOutside. If it's too late, returns nothing.
        If extended == True, show hours from 05:00-10:00 also"
        """
        target_date = datetime.date.today() + datetime.timedelta(days=day - 1)
        result = [f"{target_date.strftime('%A, %Y-%m-%d')}", "Time   | NOAA  | Temp   | ClearOutside"]

        now = datetime.datetime.now()
        today = datetime.date.today()

        # Determine cutoff behavior
        if day == 1:
            if now.hour >= 6 and now.date() > target_date:
                return ""  # It’s too late for today
            start_hour = max(18, now.hour + 1) if now.date() == target_date and now.hour >= 18 else 18
        else:
            start_hour = 18

        # Find start index (where this date's 18:00 starts in time list)
        index = 0
        current_day = 0
        while index < len(self.noaa_times):
            if self.noaa_times[index] == '00':
                current_day += 1
            if current_day == (day - 1) and self.noaa_times[index] == f"{start_hour:02d}":
                break
            index += 1

        # Pull from current day: 18–23
        while index < len(self.noaa_times):
            hour_str = self.noaa_times[index]
            hour = int(hour_str)
            if hour >= 18:
                noaa = self.noaa_cloud[index]
                temp = self.tempList[index]
                co = self.co_cloud[index]
                result.append(f"{hour:02d}:00  | {noaa:>4}% | {temp:>4}°F | {co:>10}%")
            else:
                break  # transition to next day
            index += 1

        # Pull next morning: 00–05, if extended pull till 10:00
        while index < len(self.noaa_times):
            hour_str = self.noaa_times[index]
            if extended:
                if hour_str in ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',]:
                    hour = int(hour_str)
                    noaa = self.noaa_cloud[index]
                    temp = self.tempList[index]
                    co = self.co_cloud[index]
                    result.append(f"{hour:02d}:00  | {noaa:>4}% | {temp:>4}°F | {co:>10}%")
                    index += 1
                else:
                    break
            else:   
                if hour_str in ['00', '01', '02', '03', '04', '05']:
                    hour = int(hour_str)
                    noaa = self.noaa_cloud[index]
                    temp = self.tempList[index]
                    co = self.co_cloud[index]
                    result.append(f"{hour:02d}:00  | {noaa:>4}% | {temp:>4}°F | {co:>10}%")
                    index += 1
                else:
                    break

        return "```\n" + "\n".join(result) + "\n```"



            
    def getHelp(self): #returns info on what skyBot can do
        help = "git: https://github.com/outyprouty/skyBot\n"
        help += "General: `skyBot` uses NOAA to gather some sky data and organize it for 'easy' viewing.\n\n"


        help += "`Automatic Actions`\n `Daily Checks` : Everyday at 12:05 skyBot will check the average cloud cover for the next three nights\n"
        help += "It will send a summary of the results into the 'shift-calling' channel and create observing session threads if the night is clear\n"
        help += "`Obs Session Check` : Everyday at 15:05 if an obs session is scheduled for that night skyBot will check the cloud cover again and report if its still clear or not\n"
        help += "What does a clear observing session mean? NOAA says a 4 hour period rolling average of cloud cover from sunset to sunrise is 30%" 
        help += " or less.\n"
        help += "`Popscope Check` : Everyday at 12:04 sends summary of if next three days are good for Popscope event and sends cloud cover details for tonight if it looks good\n\n"

        help += "General Commands: `skyBot graph | details | details today | popscope | ping | help | cancel | set thread(0-3)`\n"
        help += "`graph`: Gives graph of weather for next 48 hours\n"
        help += "`details`: Gives cloud cover for dark hours for next 3 days\n"
        help += "`details today`: Gives cloud cover for dark hours for today\n"
        help += "`details extended`: Gives cloud cover from time 18:00-05:00 and then from 05:00-10:00\n"
        help += "`popscope`: Gives cloud cover for sunset to 2100 for next 3 days\n"
        help += "`ping`: Displays host running skyBot\n"
        help += "`help`: Gives an explanation of skyBot and its commands\n\n"
        
        help += "Shifter Commands only available to shifter role: 'skybot cancel | uncancel | enable ms | disable ms | set thread(0-3)'\n"
        help += "`cancel`: Send in observing session thread to cancel it\n"
        help += "`uncancel`: Send in observing session thread to uncancel a previously cancelled session\n"
        help += "`enable ms`: Enable midnight shift pinging in new observing session threads (for winter months)\n"
        help += "`disable ms`: Disable midnight shift pinging in new observing session threads (for summer months)\n"
        help += "`set thread(0-3)`: Links bot to observing session thread for when it is manually created or bot is restarted\n"
        help += "Use in the thread you are trying to link with the number corresponding to how many days out the obs session is for\n"
        help += "0-today, 1-tomorrow, 2-two days away, 3-three days away"


        help += ""
        return help
    
    def getSunrise(self, day = 1):
        """
        Returns the sunrise hour (int) for the specified day.
        Adjusts for DST if DST_ACTIVE is set.
        """
        hour = self.sunriseTime(datetime.date.today() + datetime.timedelta(days = day)).hour
        return hour + 1 if DST_ACTIVE else hour

    def getSunset(self, day = 1):
        """
        Returns the sunset hour (int) for the specified day.
        Adjusts for DST if DST_ACTIVE is set.
        """
        hour = self.sunsetTime(datetime.date.today() + datetime.timedelta(days = (day - 1))).hour
        return hour + 1 if DST_ACTIVE else hour    
    
    def popScopeCheck(self, day = 1):
        # Location for Baltimore, MD
        #returns array of bolean that indicates whether cc is below 50 average for 3 hours from sunset to 21:00
        #0 index indicates whether night is clear for good popsocpe session
        sunset = self.sunsetTime(datetime.date.today() + datetime.timedelta(days = (day - 1))).hour  #Time to start tracking cc values

        range = 21 - sunset
        dayTrack = 0 #if doing prediction for other than tonight tracks what day index corresponds to
        startIndex = 0 #index of start of time and cc list
        sum = 0
        index = 0
        tempIndex = 0
        goodHours = [False] * (range + 1)
        #
        #
        while dayTrack < (day - 1):
            startIndex = startIndex + 1
            if int(self.timeList[startIndex]) == 0:
                dayTrack += 1
            
        if(day == 1):
            while(int(self.timeList[startIndex]) < sunset):
                startIndex += 1
        else:
            startIndex = startIndex + sunset + 1 #jumps to sunset hours on day of prediction
        #adds ccValue to ccAvg until end of night and adds to details string
        while (index + 1 < range):
            while(tempIndex < 2):
                sum += int(self.ccList[startIndex + index + tempIndex])
                tempIndex += 1
            if(sum < 100):
                if(goodHours[index]):
                    goodHours[0] = True
                goodHours[index + 1] = True
                goodHours[index + 2] = True
            sum = 0
            tempIndex = 0
            index += 1

        #averages ccValue for night
        return goodHours
    
    def popScopeForecast(self, day=3):
        """
        Returns string with sunset to 21:00 forecast for the given day,
        including cloud cover (%) and temperature (°F) in Markdown format.
        """
        sunset = self.sunsetTime(datetime.date.today() + datetime.timedelta(days=(day - 1))).hour

        dayTrack = 0
        index = 0
        currDate = datetime.date.today() + datetime.timedelta(days=(day - 1))
        details = [f"{currDate.strftime('%A, %Y-%m-%d')}", "Time   | NOAA  | Temp "]

        # Find starting index at sunset
        while dayTrack < (day - 1):
            index += 1
            if int(self.timeList[index]) == 0:
                dayTrack += 1

        if day == 1:
            while int(self.timeList[index]) < sunset:
                index += 1
        else:
            index += sunset

        # Now index is at sunset time
        while index < len(self.timeList):
            hour = int(self.timeList[index])
            if hour > 21:
                break

            cc_val = self.ccList[index]
            temp_val = f"{self.tempList[index]}°F"
            details.append(f"{hour:02d}:00  | {cc_val:>4}% | {temp_val:>5}")

            index += 1

        return "```text\n" + "\n".join(details) + "\n```"

    
            
        

#testing
if __name__ == "__main__":
    wc = WeatherCompiler()
    print(wc.ccForecast(1))
    print(wc.ccAverage(1))
    print()
    print(wc.ccForecast())
    print(wc.getHelp())
    print(wc.sunriseTime(datetime.date.today() + datetime.timedelta(days = 1)))
    print(wc.sunsetTime(datetime.date.today()))  #Time to start tracking cc values
