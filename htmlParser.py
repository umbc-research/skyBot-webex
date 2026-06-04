# Enhanced htmlParser.py — extracts 72 hours of Total Cloud Cover from ClearOutside
import requests
from bs4 import BeautifulSoup

NOAA_URL_48H = "https://forecast.weather.gov/MapClick.php?w3u=1&w4=sky&w10u=0&w13u=1&AheadHour=0&Submit=Submit&FcstType=digital&textField1=39.2589&textField2=-76.7139&site=all&unit=0&dd=&bw="
NOAA_URL_72H = "https://forecast.weather.gov/MapClick.php?w3u=1&w4=sky&w10u=0&w13u=1&AheadHour=0&FcstType=digital&textField1=39.2589&textField2=-76.7139&site=all&unit=0&dd=&bw=&AheadDay.x=40&AheadDay.y=15"
CLEAROUTSIDE_URL = "https://clearoutside.com/forecast/39.27/-76.73"

def fetch_html(url):
    response = requests.get(url)
    response.raise_for_status()
    return BeautifulSoup(response.text, 'html.parser')

def extract_noaa_data(soup, row_index):
    try:
        row_list = soup.select(".contentArea table[width='800']")[2].find_all("tr")
        data = [b.get_text() for b in row_list[row_index].find_all("b")]
        return data[1:] if data and "Hour" in data[0] else data
    except (AttributeError, IndexError):
        return []

def get_noaa_forecast():
    soup_48h = fetch_html(NOAA_URL_48H)
    soup_72h = fetch_html(NOAA_URL_72H)
    times = extract_noaa_data(soup_48h, 2) + extract_noaa_data(soup_48h, 6) + extract_noaa_data(soup_72h, 2) + extract_noaa_data(soup_72h, 6)
    cloud = extract_noaa_data(soup_48h, 3) + extract_noaa_data(soup_48h, 7) + extract_noaa_data(soup_72h, 3) + extract_noaa_data(soup_72h, 7)
    return times, cloud

def get_clearoutside_forecast():
    try:
        soup = fetch_html(CLEAROUTSIDE_URL)
        days = soup.find_all("div", class_="fc_day")

        full_values = []
        for day_index, day in enumerate(days):
            detail_rows = day.find_all("div", class_="fc_detail_row")
            for row in detail_rows:
                label = row.find("span", class_="fc_detail_label")
                if label and "total clouds" in label.get_text(strip=True).lower():
                    ul = row.find("div", class_="fc_hours").find("ul")
                    if not ul:
                        continue
                    lis = ul.find_all("li")
                    values = [li.get_text(strip=True).replace('%', '') for li in lis if li.get_text(strip=True)]
                    full_values.extend(values)
                    break  # Stop searching other rows in this day

        hours = [f"{i:02d}" for i in range(len(full_values))]
        return hours, full_values
    except Exception as e:
        print(f"Error reading ClearOutside: {e}")
        return [], []

def pair_forecasts(times, noaa, clear):
    output = []
    for i in range(len(times)):
        t = times[i] if i < len(times) else "--"
        n = noaa[i] if i < len(noaa) else "--"
        c = clear[i] if i < len(clear) else "--"
        output.append((t.zfill(2), n, c))
    return output

def generateTimeList():
    times, _ = get_noaa_forecast()
    return times

def generateCCList():
    _, cloud = get_noaa_forecast()
    return cloud

def generateTempList():
    def extract_temps_from_soup(soup):
        tempData = []
        rowList = soup.body.main.find(attrs={"class": "contentArea"}).find_all("table", attrs={"width": "800"}, limit=3)[2].find_all("tr")

        for i, row in enumerate(rowList):
            cells = row.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()
            if "temperature" in label:
                b_tags = row.find_all("b")
                for b in b_tags:
                    text = b.get_text(strip=True)
                    tempData.append(text if text else "500")
        return tempData

    # NOAA 0–48 hours
    url1 = 'https://forecast.weather.gov/MapClick.php?w0=t&w3u=1&w4=sky&w13u=0&w14u=1&AheadHour=0&Submit=Submit&FcstType=digital&textField1=39.2589&textField2=-76.7139&site=all&unit=0&dd=&bw='
    soup1 = fetch_html(url1)
    temps1 = extract_temps_from_soup(soup1)

    # NOAA 49–72 hours
    url2 = 'https://forecast.weather.gov/MapClick.php?w0=t&w3u=1&w4=sky&w13u=0&w14u=1&AheadHour=0&FcstType=digital&textField1=39.2589&textField2=-76.7139&site=all&unit=0&dd=&bw=&AheadDay.x=40&AheadDay.y=15'
    soup2 = fetch_html(url2)
    temps2 = extract_temps_from_soup(soup2)

    return temps1 + temps2



if __name__ == '__main__':
    noaa_times, noaa_cloud = get_noaa_forecast()
    co_times, co_cloud = get_clearoutside_forecast()
    paired = pair_forecasts(noaa_times, noaa_cloud, co_cloud)

    with open("output_comparison.txt", "w") as f:
        f.write("Time | NOAA Cloud Cover | ClearOutside Cloud Cover\n")
        f.write("-----|------------------|-------------------------\n")
        for t, n, c in paired:
            f.write(f"{t}   | {n:>16}% | {c:>23}%\n")

    print("Output saved to output_comparison.txt")