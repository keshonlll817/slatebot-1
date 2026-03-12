import discord
import csv
import io
import re
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("No TOKEN found.")

ALLOWED_CHANNELS = [
1471792196582637728,
1474078126630768822,
1479241150996152340
]

FOUR_PLUS_CHANNEL = 1443356395935240302
TOTALS_CHANNEL = 1446203029916356649
TEST_CHANNEL = 1471792196582637728

EST = ZoneInfo("America/New_York")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

last_slate_messages = []

# ==============================
# UTIL FUNCTIONS
# ==============================

def format_units(u):
    if u == 1: return "1U"
    if u == 1.25: return "1.25U"
    if u == 1.5: return "1.5U"
    if u == 1.75: return "1.75U"
    if u == 2: return "2U"
    if u == 2.5: return "2.5U"
    if u == 3: return "3U"
    return f"{u}U"

def convert_league(name):
    name=name.lower()
    if "elite" in name: return "ELITE"
    if "setka" in name: return "SETKA"
    if "czech" in name: return "CZECH"
    if "cup" in name: return "CUP"
    return name.upper()

def parse_time(est_time):
    dt=datetime.strptime(est_time,"%m/%d %I:%M %p")
    est=dt.strftime("%I:%M %p")
    pst_dt=dt.replace(hour=(dt.hour-3)%24)
    pst=pst_dt.strftime("%I:%M %p")
    return est,pst

async def send_long_message(channel,text):

    chunks=[]

    while len(text)>2000:
        split_index=text.rfind("\n",0,2000)

        if split_index==-1:
            split_index=2000

        chunks.append(text[:split_index])
        text=text[split_index:]

    chunks.append(text)

    messages=[]

    for chunk in chunks:
        msg=await channel.send(chunk.strip())
        messages.append(msg)

    return messages


# ==============================
# RECAP PARSERS
# ==============================

async def parse_four_plus(channel,start,end,limit=None):

    wins=losses=washes=0
    normal_w=normal_l=0
    nuke_w=nuke_l=0
    caution_w=caution_l=0

    seen=set()

    async for msg in channel.history(limit=limit):

        msg_time=msg.created_at.astimezone(EST)

        if start and not(start<=msg_time<end):
            continue

        for line in msg.content.split("\n"):

            line=line.strip()

            # FIX 1: normalize emoji spacing
            line=line.replace(")❌", ") ❌").replace(")✅", ") ✅")

            # FIX 2: allow "vs" and "v"
            if "vs" not in line and " v " not in line:
                continue

            if "U @" in line or "U@" in line:
                continue

            if line in seen:
                continue

            seen.add(line)

            is_nuke="☢️" in line
            is_caution="⚠️" in line

            if "🧼" in line:
                washes+=1
                continue

            if "✅" in line:

                wins+=1

                if is_nuke:
                    nuke_w+=1
                elif is_caution:
                    caution_w+=1
                else:
                    normal_w+=1

            elif "❌" in line:

                losses+=1

                if is_nuke:
                    nuke_l+=1
                elif is_caution:
                    caution_l+=1
                else:
                    normal_l+=1

    return wins,losses,washes,normal_w,normal_l,caution_w,caution_l,nuke_w,nuke_l


async def parse_totals(channel,start,end,limit=None):

    wins=losses=0
    units=0

    seen=set()

    async for msg in channel.history(limit=limit):

        msg_time=msg.created_at.astimezone(EST)

        if start and not(start<=msg_time<end):
            continue

        for line in msg.content.split("\n"):

            line=line.strip()

            # FIX 1: normalize emoji spacing
            line=line.replace(")❌", ") ❌").replace(")✅", ") ✅")

            # FIX 2: allow "vs" and "v"
            if "vs" not in line and " v " not in line:
                continue

            if line in seen:
                continue

            seen.add(line)

            unit_match=re.search(r'(\d+(\.\d+)?)U',line,re.IGNORECASE)

            if not unit_match:
                continue

            stake=float(unit_match.group(1))

            if "✅" in line:
                wins+=1
                units+=stake/1.2

            elif "❌" in line or "🪝" in line:
                losses+=1
                units-=stake

    return wins,losses,units


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):

    global last_slate_messages

    if message.author.bot:
        return

    content=message.content.lower().strip()

# ==============================
# RECAP COMMANDS
# ==============================

    if content.startswith("!recap"):

        now=datetime.now(EST)

        if "test" in content:

            start=None
            end=None
            limit=50
            title=f"TEST RECAP — {now.strftime('%b')} {now.day} (EST)"

        elif "today" in content:

            start=now.replace(hour=0,minute=0,second=0,microsecond=0)
            end=now
            title=f"TODAY RECAP — {now.strftime('%b')} {now.day} (EST)"
            limit=None

        elif "lifetime" in content:

            start=None
            end=None
            title="LIFETIME RECAP"
            limit=None

        elif "daily" in content:

            start=(now-timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
            end=start+timedelta(days=1)
            title=f"DAILY RECAP — {start.strftime('%b')} {start.day} (EST)"
            limit=None

        elif "monthly" in content:

            start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            end=now
            title=f"MONTHLY RECAP — {now.strftime('%b %Y')}"
            limit=None

        else:
            return

        if message.channel.id==TEST_CHANNEL:
            four_channel=message.channel
            totals_channel=message.channel
        else:
            four_channel=client.get_channel(FOUR_PLUS_CHANNEL)
            totals_channel=client.get_channel(TOTALS_CHANNEL)

        fw,fl,fwash,nw,nl,cw,cl,kw,kl=await parse_four_plus(four_channel,start,end,limit)
        tw,tl,tunits=await parse_totals(totals_channel,start,end,limit)

        four_units=( (nw*1.1)-(nl*3) + (cw*0.55)-(cl*1.5) + (kw*2.2)-(kl*6) )

        recap=f"📊 **{title}**\n\n"

        recap+="🏓 **4+ PLAYS**\n"

        if fw+fl+fwash==0:
            recap+="No plays graded.\n\n"
        else:
            recap+=f"Record: {fw}-{fl}"

            if fwash>0:
                recap+=f" ({fwash} Wash)"

            recap+=f"\nUnits: {four_units:+.2f}U\n\n"

            recap+=f"Normal {nw}-{nl}\n"
            recap+=f"⚠️ {cw}-{cl}\n"
            recap+=f"☢️ {kw}-{kl}\n\n"

        recap+="🏓 **TOTAL PLAYS**\n"

        if tw+tl==0:
            recap+="No plays graded."
        else:
            recap+=f"Record: {tw}-{tl}\n"
            recap+=f"Units: {tunits:+.2f}U"

        await message.channel.send(recap)
        return


# ==============================
# BASIC COMMANDS
# ==============================

    if message.channel.id not in ALLOWED_CHANNELS:
        return

    if content=="ping":
        await message.channel.send("pong")
        return


# ==============================
# CSV SLATE ENGINE (UNCHANGED)
# ==============================

    if not message.attachments:
        return

    attachment = message.attachments[0]

    if not attachment.filename.endswith(".csv"):
        return

    file_bytes = await attachment.read()
    decoded = file_bytes.decode("utf-8")

    reader = csv.DictReader(io.StringIO(decoded))

    four_plus={}
    totals={}

    for row in reader:

        league=convert_league(row["League"])
        p1=row["Player 1"]
        p2=row["Player 2"]
        play=row["Play"]
        history=row["History"]
        est_time=row["Time (Eastern)"]

        est,pst=parse_time(est_time)

        if "4+" in play:

            match=re.search(r"\((\d+)/(\d+)\)",history)

            if not match:
                continue

            losses=int(match.group(1))
            total=int(match.group(2))
            wins=total-losses
            pct=wins/total

            tier="normal"

            if total>=40 and pct>=0.91:
                tier="nuke"
            elif wins<=22:
                tier="caution"

            key=f"{league}{p1}{p2}{est}"

            four_plus[key]=(league,p1,p2,est,pst,wins,total,tier)

        elif "Over/Under" in history:

            match=re.search(r"\((\d+)/(\d+)\)",history)

            if not match:
                continue

            wins=int(match.group(1))
            total=int(match.group(2))
            pct=wins/total

            if total>=30:

                if pct>=.95: units=2.5
                elif pct>=.91: units=2
                elif pct>=.86: units=1.5
                elif pct>=.81: units=1.25
                else: units=1

            else:

                if pct>=.95: units=2
                elif pct>=.91: units=1.75
                elif pct>=.86: units=1.5
                elif pct>=.81: units=1.25
                else: units=1

            key=f"{league}{p1}{p2}{est}{play}"

            totals[key]=(league,p1,p2,play,units,est,pst,wins,total)

    old_messages=last_slate_messages.copy()
    last_slate_messages=[]

    await message.delete()

    msg1=await message.channel.send("🏓 **4+ PLAYS** 🏓")
    last_slate_messages.append(msg1)

    if four_plus:

        text=""

        for v in four_plus.values():

            league,p1,p2,est,pst,wins,total,tier=v

            emoji=""
            if tier=="nuke": emoji=" ☢️"
            elif tier=="caution": emoji=" ⚠️"

            text+=f"{league} – {p1} vs {p2} @ {est} EST / {pst} PST ({wins}/{total}){emoji}\n\n"

        sent_msgs=await send_long_message(message.channel,text.strip())
        last_slate_messages.extend(sent_msgs)

    msg3=await message.channel.send("🏓 **TOTAL PLAYS** 🏓")
    last_slate_messages.append(msg3)

    if totals:

        text=""

        for v in totals.values():

            league,p1,p2,play,units,est,pst,wins,total=v

            text+=f"{league} – {p1} vs {p2} {play} {format_units(units)} @ {est} EST / {pst} PST ({wins}/{total})\n\n"

        sent_msgs=await send_long_message(message.channel,text.strip())
        last_slate_messages.extend(sent_msgs)


client.run(TOKEN)
