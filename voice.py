# coding: utf-8

from pathlib import Path
import re
import urllib
import json
import random

from emoji import emojize, demojize

import discord
from discord.ext import commands

CONNECTIN_TIME_OUT = 30

class Voice(commands.Cog):
    def __init__(self, bot:commands.Bot):
        # super().__init__(bot)
        self.bot = bot
        self.queue = {}
        self.emoji = {}
        self.EMOJI_LIST = self.load_emoji_list()
        self.SERVER_EMOJI_LIST = self.load_server_emoji_list()

    def load_emoji_list(self):
        with open('config.json', 'r') as file:
            config = json.load(file)

        return config.get('emoji_list', {})

    def load_server_emoji_list(self):
        with open('config.json', 'r') as file:
            config = json.load(file)

        return config.get('server_emoji_list', {})
    
    @commands.slash_command(name="first_slash", guild_ids=[747509186228650015])
    async def first_slash(ctx): 
        await ctx.respond("You executed the slash command!")

    @commands.command()
    async def join(self, ctx):
        '''Joins current voice channel'''
        vc = None
        if ctx.author.voice:
            vc = await self._connect(ctx.author.voice.channel)
        if not vc:
            await ctx.message.add_reaction('🥺')
    
    # def is_connected(self, guild):
    #     return True if self.get_vc(voice_channel) else False

    def get_vc(self, voice_channel):
        for vclient in self.bot.voice_clients:
            if vclient.channel == voice_channel:
                return vclient
        return None

    async def _connect(self, voice_channel):
        if voice_channel:
            vc = self.get_vc(voice_channel)
            if not vc:
                vc = await voice_channel.connect(reconnect=False)
                # initialize
                self.queue[vc.session_id] = []
            return vc
        return None

    def dequeue(self, vc):
        # if self.queue:
        #    return self.queue.pop(0)
        # else:
        #    return None
        return self.queue[vc.session_id].pop(0) if self.queue[vc.session_id] else None
    
    def _vc_play(self, vc):
        '''Before calling this method, you must join voiceClient'''
        if url:= self.dequeue(vc):
            def after(e):
                self._vc_play(vc)
            vc.play(discord.FFmpegPCMAudio(url, stderr=False), after=after)
        return None

    def play(self, vc, url):
        self.queue[vc.session_id].append(url)
        if not vc.is_playing():
            self._vc_play(vc)

    @commands.command()
    async def leave(self, ctx):
        '''Leaves the voice channel'''
        vc = None
        if ctx.author.voice:
            vc = self.get_vc(ctx.author.voice.channel)
        else:
            for c in ctx.guild.voice_channels:
                vc = self.get_vc(c)
                if vc:
                    break
        if vc:
            await vc.disconnect()

    # EMOJI_LIST = {
    #     'Japan': [{'source':r'/app/sounds/kimigayo01.mp3','freq':100}],
    #     'beer_mug': [{'source':r'/app/sounds/deutshche.mp3','freq':100}],
    #     'bellhop_bell': [{'source':r'/app/sounds/bell.wav','freq':100}],
    #     'pile_of_poo': [{'source':r'/app/sounds/shinda.mp3','freq':100}],
    #     'Japanese_open_for_business_button': [{'source':r'/app/sounds/nc148600.wav','freq':100}],
    #     'french_fries': [{'source':r'/app/sounds/potato.mp3','freq':100}],
    # }
    # SERVER_EMOJI_LIST = {
    #     'hammerandsickle': [{'source':r'/app/sounds/ussr.wav','freq':80},{'source':r'/app/sounds/usssr.wav','freq':20}],
    #     'symmetryIshihara': [{'source':r'/app/sounds/ishr.wav','freq':100}],
    #     'symmetricalIshihara': [{'source':r'/app/sounds/rhsi.wav','freq':100}],
    #     'nerunerunerune': [{'source':r'/app/sounds/nc31909.mp3','freq':100}],
    #     'professional': [{'source':r'/app/sounds/nc148600.wav','freq':100}],
    #     'windowsxp': [
    #         {'source':r'/app/sounds/windows-xp-shutdown.wav','freq':2},
    #         {'source':r'/app/sounds/windows-xp-startup.wav','freq':8},
    #         {'source':r'/app/sounds/windows-xp-critical-stop_C_major.wav','freq':40},
    #         {'source':r'/app/sounds/windows-xp-ding_B_major.wav','freq':30},
    #         {'source':r'/app/sounds/windows-xp-error.wav','freq':20},
    #         ],
    #     'nyanchu': [{'source':r'/app/sounds/nc141260.mp3','freq':100}],
    #     'zundamon': [{'source':r'/app/sounds/shigotoshirokasu.wav','freq':100}],
    # }

    # def ussr(self):
    #     USSR = r'/app/sounds/ussr.wav'
    #     USSSR = r'/app/sounds/usssr.wav'
    #     if random.randint(1,5) == 1:
    #         return USSSR
    #     return USSR
    
    # def ishr(self):
    #     ishr = r'/app/sounds/ishr.wav'
    #     ishr2 = r'/app/sounds/ishr2.wav'
    #     if random.randint(1,5) == 1:
    #         return ishr2
    #     return ishr
    
    # def rhsi(self):
    #     return r'/app/sounds/rhsi.wav'
    
    # def bell(self):
    #     return r'/app/sounds/bell.wav'
    
    # def de(self):
    #     return r'/app/sounds/deutshche.mp3'
   
    def atsumori(self):
        NORMAL = r'/app/sounds/apologize.wav'
        NORMAL_P = r'/app/sounds/apologize_1.wav'
        NORMAL_S = r'/app/sounds/apologize_3.wav'
        KUDOS = r'/app/sounds/situreisimasita.wav'
        KUDOS_P = r'/app/sounds/situreisimasita_1.wav'
        KUDOS_S = r'/app/sounds/situreisimasita_3.wav'
        STD = r'/app/sounds/atsumori_std.wav'
        LONG = r'/app/sounds/atsumori_long.wav'
        USSR = r'/app/sounds/ussr.wav'
        ls = [STD]
        if random.randint(1, 100) <= 20:
            ls = [LONG]
        if random.randint(1, 100) <= 5:
            ls = [USSR]
            return ls
            # ls.append(USSR)
        r = random.randint(1, 100)
        if r <= 10:
            ls += [KUDOS_P]+ls+[KUDOS_S]
            # if r <= 5:
            #     ls += [NORMAL_P]+ls[1:]+[NORMAL_S]
        elif r <= 20:
            ls += [NORMAL_P]+ls+[NORMAL_S]
            # if r <= 15:
            #     ls += [KUDOS_P]+ls[1:]+[KUDOS_S]
        elif r <= 60:
            ls.append(KUDOS)
        elif r <= 100:
            ls.append(NORMAL)
        return ls

    def play_atsumori(self, vc):
        ls = self.atsumori()
        # print(f'Say {len(ls)} messages at {vc.guild.name}')
        for url in ls:
            self.play(vc, url)
    
    @commands.Cog.listener(name='on_ready')
    async def on_ready_method(self):
        # print('on ready')
        await self.bot.change_presence(activity=discord.Game(f'{self.bot.command_prefix}join'))

    @commands.Cog.listener(name='on_message')
    async def on_message_atsumori(self, message):
        r = random.randint(1, 100)
        text = demojize(message.content, delimiters=("<:", ":>"))
        res = re.findall(r"<:([^<>]+?):[0-9]*?>", text)
        for x in res:
            print(x)
            if x in self.EMOJI_LIST or x == 'hot_springs':
                await message.add_reaction(emojize(':'+x+':'))
            if x in self.SERVER_EMOJI_LIST or x == 'atsumori':
                for emoji in message.guild.emojis:
                    if emoji.name == x:
                        await message.add_reaction(emoji)
        if r <= 10:
            atsumori = '♨️'
            for emoji in message.guild.emojis:
                if emoji.name == 'atsumori':
                    atsumori = emoji
            await message.add_reaction(atsumori)
    
    async def reaction_method_pre(self, message, user_id):
        # search member
        member = await message.guild.fetch_member(user_id)
        if not member.voice:
            member = await message.guild.fetch_member(message.author.id)
        if not member.voice:
            return
        voice_channel = member.voice.channel
        return await self._connect(voice_channel)
        # await self._connect(message.guild.voice_channels[0])

    def reaction_method_list(self, emoji, list, key):
        if len(list[key]) > 1:
            n = 0
            k = 0
            for x in list[key]:
                n += x["freq"]
            p = random.randint(1,n)
            for x in list[key]:
                k += x["freq"]
                if p <= k:
                    return x["source"]
        else:
            return list[key][0]["source"]

    async def reaction_method(self, message, user_id, emoji):
        # print(emoji.name)
        if emoji.name == 'atsumori' or emoji.name == '♨':
            vc = await self.reaction_method_pre(message, user_id)
            if message.content is not None:
                self.play_atsumori(vc)
        elif demojize(str(emoji), delimiters=("","")) in self.EMOJI_LIST:
            vc = await self.reaction_method_pre(message, user_id)
            if message.content is not None:
                self.play(vc, self.reaction_method_list(emoji, self.EMOJI_LIST, demojize(str(emoji), delimiters=("",""))))
        elif emoji.name in self.SERVER_EMOJI_LIST:
            vc = await self.reaction_method_pre(message, user_id)
            if message.content is not None:
                self.play(vc, self.reaction_method_list(emoji, self.SERVER_EMOJI_LIST, emoji.name))

    @commands.Cog.listener(name='on_raw_reaction_add')
    async def on_reaction_add_weblio(self, payload:discord.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await self.reaction_method(message, payload.user_id, payload.emoji)
    
    @commands.Cog.listener(name='on_raw_reaction_remove')
    async def on_reaction_remove_weblio(self, payload:discord.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)  
        message = await channel.fetch_message(payload.message_id)
        await self.reaction_method(message, payload.user_id, payload.emoji)

async def setup(bot):
    await bot.add_cog(Voice(bot))

async def teardown(bot):
    pass