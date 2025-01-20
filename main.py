import re
from io import BytesIO
from enum import Enum
from dataclasses import dataclass
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
from pdfminer.high_level import extract_text


load_dotenv("bot.env")
BOT_API_KEY = os.getenv("BOT_API_KEY")
ELIGIBILITY_LOG_CHANNEL_ID = os.getenv("ELIGIBILITY_LOG_CHANNEL_ID")


class StudentType(Enum):

    NEW_UNDERGRADUATE = 0
    CONTINUING_UNDERGRADUATE = 1
    NEW_GRADUATE = 2
    CONTINUING_GRADUATE = 3

    def is_new(self):

        return self == StudentType.NEW_GRADUATE or self == StudentType.NEW_UNDERGRADUATE

    def is_undergratuate(self):

        return self == StudentType.CONTINUING_UNDERGRADUATE or self == StudentType.NEW_UNDERGRADUATE

    def is_graduate(self):

        return self == StudentType.CONTINUING_GRADUATE or self == StudentType.NEW_GRADUATE


@dataclass
class Student:

    student_type: StudentType
    gpa: float
    current_credit_hours: int

    @staticmethod
    def txt_to_student_type(txt) -> StudentType:

        x = re.search("Student Type\n.*\n", txt)

        # Makes a new string containing only the student type
        txt2 = txt[x.span()[0]:x.span()[1]]

        # Isolates the actual student type, excluding the header
        x = re.search("\n.*\n", txt2)
        student_type = txt2[x.span()[0]+1:x.span()[1]-1]
        
        return getattr(
            StudentType,
            student_type.replace(" ", "_").upper()
        )

    @staticmethod
    def txt_to_num_credit_hours(txt) -> int:

        # Shortens the total transcript to only the relevant part.
        x = re.search("Credit Hours", txt)
        txt3 = txt[x.span()[1]:]
        
        # Goes through the current classes, looks for their credit values, and adds it to the 'CreditHours' list.
        credit_hours = []
        while len(txt3) > 0:
            x = re.search("[123456789]*[123456789][.]000", txt3)
            if not x:
                break
            else:
                credit_hours.append(txt3[x.span()[0]:x.span()[1]])
                txt3 = txt3[x.span()[1]:]
        
        # sums values converted to floats
        return sum(map(float, credit_hours))

    @staticmethod
    def txt_to_gpa(txt) -> int:
        
        # Searches the document for the specific point where it mentions total, overall GPA.
        # It's a little weird, but on the unofficial transcript, this is the only one that has 2 line breaks before the GPA numbers.
        # It's because it says (undergraduate) which adds another line break.
        x = re.search("GPA\n\n....\n....\n....\n", txt)

        # Takes the location of the actual GPA numbers from the document
        gpaLOC = x.span()[1]
        gpaLOCNUM1 = int(gpaLOC-5)
        gpaLOCNUM2 = int(gpaLOC-1)

        return float(txt[gpaLOCNUM1:gpaLOCNUM2])

    @classmethod
    def from_txt(cls, txt: str):

        student_type = cls.txt_to_student_type(txt)
        total_credit_hours = cls.txt_to_num_credit_hours(txt)

        if student_type.is_new():
            return cls(student_type=student_type, gpa=0.0, credit_hours=total_credit_hours)

        gpa = cls.txt_to_gpa(txt)
        return cls(student_type=student_type, gpa=gpa, current_credit_hours=total_credit_hours)

    def is_eligible(self) -> bool:

        has_acceptable_gpa = any([
            self.student_type == StudentType.CONTINUING_GRADUATE and self.gpa >= 2.5,
            self.student_type == StudentType.CONTINUING_UNDERGRADUATE and self.gpa >= 2.0,
            self.student_type.is_new()
        ])

        is_full_time = any([
            self.student_type.is_graduate() and self.current_credit_hours >= 9,
            self.student_type.is_undergratuate() and self.current_credit_hours >= 12
        ])

        return has_acceptable_gpa and is_full_time


class TranscriptCheckingBot(commands.Bot):

    def __init__(self, *args, log_channel_id: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.log_channel_id = log_channel_id
        self.log_channel = None  # Placeholder for the log channel

    async def on_ready(self):
        self.log_channel = self.get_channel(self.log_channel_id)
        await self.tree.sync()

def main():

    # initialize the bot
    intents = discord.Intents.default()
    intents.message_content = True

    help_command = commands.DefaultHelpCommand(
        no_category="Commands",
        sort_commands=False,
    )
    bot = TranscriptCheckingBot(command_prefix="+", intents=intents, help_command=help_command, log_channel_id=ELIGIBILITY_LOG_CHANNEL_ID)

    @bot.tree.command(name="ping", description="pings the bot to see if it's online")
    async def ping(interaction: discord.Interaction):

        await interaction.response.send_message(f"pong :ping_pong: ({bot.latency * 1.0e+3:.1f} ms)")

    @bot.tree.command(name="process_transcript", description="Checks your transcript for eligibility")
    async def process_transcript(interaction: discord.Interaction, file: discord.Attachment):

        if not file.filename.endswith(".pdf"):
            await interaction.response.send_message("Please upload a pdf file")
            return

        # await interaction.response.defer()

        pdf_bytes = await file.read()
        with BytesIO(pdf_bytes) as buffer:
            txt = extract_text(buffer)

        student = Student.from_txt(txt)
        if student.is_eligible():
            user_response = "Success! Your eligibility has been logged ✅"
            log_message = f"<@{interaction.user.id}> ({interaction.user.name}) is eligible ✅"
        else:
            user_response = "You are not eligible. Please contact an officer if you believe this was a mistake."
            log_message = f"<@{interaction.user.id}> ({interaction.user.name}) is not eligible ❌"

        await interaction.response.send_message(user_response, ephemeral=True)
        await bot.log_channel.send(log_message)
        return

    bot.run(BOT_API_KEY)


if __name__ == "__main__":

    main()