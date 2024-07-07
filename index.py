import os
import logging
import discord
import asyncio
from discord.ext import commands, voice_recv
import numpy as np
import vosk
from vosk import Model, KaldiRecognizer
import json


# Hard-coded Discord token
DISCORD_TOKEN = '.....'

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_current_date_string():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

# Function to convert stereo audio to mono
def convert_audio(input):
    try:
        data = np.frombuffer(input, dtype=np.int16)
        mono_data = data[::2]
        return mono_data.tobytes()
    except Exception as e:
        logger.error(f"convert_audio: {e}")
        raise e

# Ensure necessary directories exist
if not os.path.exists('./data/'):
    os.makedirs('./data/')

# Load Vosk models
vosk.SetLogLevel(-1)
models = {
    'en': Model('vosk_models/en')
    # Add other languages if needed
}
recognizers = {lang: KaldiRecognizer(model, 48000) for lang, model in models.items()}

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.voice_states = True

# Create bot
bot = commands.Bot(command_prefix='*', intents=intents)
guild_map = {}

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')

@bot.command(name='join')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send('Error: please join a voice channel first.')
        return
    channel = ctx.author.voice.channel
    if ctx.guild.id in guild_map:
        await ctx.send('Already connected.')
    else:
        await connect(ctx, channel)

@bot.command(name='leave')
async def leave(ctx):
    if ctx.guild.id in guild_map:
        voice_client = guild_map[ctx.guild.id]['voice_client']
        await voice_client.disconnect()
        del guild_map[ctx.guild.id]
        await ctx.send("Disconnected.")
    else:
        await ctx.send("Cannot leave because not connected.")

## @bot.command(name='help')
## async def help_command(ctx):
##     help_text = "**COMMANDS:**\n"
##     help_text += "```*join\n"
##     help_text += "*leave\n"
##     help_text += "*lang <code>\n"
##     help_text += "```"
##     await ctx.send(help_text)

@bot.command(name='lang')
async def set_lang(ctx, lang):
    if ctx.guild.id in guild_map:
        guild_map[ctx.guild.id]['selected_lang'] = lang
        await ctx.send(f"Language set to {lang}.")
    else:
        await ctx.send("Error: Bot is not connected to a voice channel.")

async def connect(ctx, channel):
    try:
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        guild_map[ctx.guild.id] = {
            'voice_client': voice_client,
            'text_channel': ctx.channel,
            'selected_lang': 'en',
            'debug': False,
        }
        await ctx.send('Connected!')
        listen_to_audio(voice_client, ctx.guild.id)
    except Exception as e:
        logger.error(f"connect: {e}")
        await ctx.send('Error: unable to join your voice channel.')

def listen_to_audio(voice_client, guild_id):
    class MySink(voice_recv.AudioSink):
        def __init__(self):
            super().__init__()

        def wants_opus(self):
            return False

        def write(self, user, data: voice_recv.VoiceData):
            buffer = convert_audio(data.pcm)
            transcription = transcribe(buffer, guild_id)
            if transcription:
                asyncio.run_coroutine_threadsafe(
                    guild_map[guild_id]['text_channel'].send(f"{user.name}: {transcription}"),
                    bot.loop
                )

        def cleanup(self):
            pass

    sink = MySink()
    voice_client.listen(sink)

def transcribe(buffer, guild_id):
    lang = guild_map[guild_id]['selected_lang']
    recognizer = recognizers[lang]
    recognizer.AcceptWaveform(buffer)
    result = recognizer.Result()
    text = json.loads(result).get('text', '')
    logger.info(f'vosk: {text}')
    return text

bot.run(DISCORD_TOKEN)
