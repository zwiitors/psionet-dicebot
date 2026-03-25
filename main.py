# 0.1.14
import discord
from discord.ui import Button, View
from discord.ext import commands
from discord import app_commands
import random
from collections import defaultdict
import asyncio
import dotenv
import os
from aiohttp import web  # Webサーバー用に追記

# ボットのトークンを設定してください

# 定数
WAIT_TIME = 0.07

dotenv.load_dotenv()
TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or dotenv.get_key(
    ".env", "DISCORD_BOT_TOKEN"
)  # Renderの環境変数対応のため修正
client = discord.Client(intents=discord.Intents.all())
bot = commands.Bot(intents=discord.Intents.all(), command_prefix="/")


# --- ダミーWebサーバーの設定 ---
async def handle_ping(request):
    """ヘルスチェック用のレスポンスを返す"""
    return web.Response(text="Bot is running")


async def start_web_server():
    """Webサーバーをバックグラウンドで起動する"""
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()

    # Renderは環境変数PORTでリッスンするポートを指定する
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")


async def setup_hook():
    """ボット起動時にWebサーバーのタスクを追加する"""
    bot.loop.create_task(start_web_server())
    await bot.tree.sync()


# -------------------------------


# 成功率ごとの試行回数を保持する辞書
class VariablesManager:
    achievement_bonuses = defaultdict(int)
    success_attempts = defaultdict(int)
    used_mps = defaultdict(int)
    function_ids = defaultdict(int)
    result_container = defaultdict(list)
    ctx_history = defaultdict(list)
    reroll_cost = defaultdict(lambda: 7)
    messages = defaultdict(list)


class DiceManager:
    def __init__(self):
        self.achievement_bonus = 0
        self.attempts = 0
        self.used_mp = 0
        self.reroll_num = 0
        self.modify_cost = 0
        self.function_id = 0


async def send_multiple_message(messages, ctx):
    print("awaitng for send message")
    await ctx.send("\n".join(messages))
    print("successfully send message")


@bot.command()
async def damage(ctx, *args):
    args = list(args)

    # ダイスの内容を解析して処理
    aws = []
    for result, mult, dice_results, exp in calculate_damage(args):
        print("awaiting for send reply")
        aws.append(
            ctx.reply(
                f"Damage: {int(result)}x{mult:.1f}->{int(result * mult)} \nDice Results: {dice_results}\nExpected Value: {int(exp)}"
            )
        )
        print("successfully send reply")
    await asyncio.gather(*aws)


# ダイスの内容を解析してダメージを計算
def calculate_damage(args):
    command = [""] + args
    if len(command) >= 2:
        damage_roll = command[1]
    achievement = [1]
    if len(command) > 2:
        achievement = list(map(lambda x: min(6, int(x)), command[2].split(",")))
    damage = damage_roll.split("+")
    minus_damage = ["0"]
    for i, d in enumerate(damage):
        if "-" in d:
            md = d.split("-")
            damage[i] = md[0]
            minus_damage.extend(md[1:])
    for a in achievement:
        result = 0
        exp = 0
        dices = []
        for d in damage:
            dd = list(map(int, d.split("d")))
            if len(dd) == 2:
                for _ in range(dd[0]):
                    dice = random.randint(1, dd[1])
                    result += dice
                    exp += (1 + dd[1]) / 2
                    dices.append(dice)
            elif len(dd) == 1:
                result += dd[0]
                exp += dd[0]
        for md in minus_damage:
            dd = list(map(int, md.split("d")))
            if len(dd) == 2:
                for _ in range(dd[0]):
                    dice = random.randint(1, dd[1])
                    result -= dice
                    exp -= (1 + dd[1]) / 2
                    dices.append(dice)
            elif len(dd) == 1:
                result -= dd[0]
                exp -= dd[0]
        mult = (a - 1) * 0.5 + 1
        yield result, mult, dices, exp


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


@bot.command()
async def roll(ctx, success_rate, achievement_bonus="0"):
    """1d100ロールを行うコマンド"""

    def dice_loop(
        attempts,
        result,
    ):
        while True:
            if attempts >= 5:
                break
            success_rate = target_results[attempts]
            result = random.randint(1, 100)

            if result <= success_rate:
                VariablesManager.messages[user_id].append(
                    f"1d100({success_rate}%)->{result}"
                )
                attempts += 1
                continue
            else:
                VariablesManager.messages[user_id].append(
                    f"1d100({success_rate}%)->{result}: Failure"
                )
                break
        return result, attempts

    async def interlude(
        repeat,
    ):
        def check(m):
            if m.author != ctx.author or m.channel != ctx.channel:
                return False
            if m.content[:5] == "/roll":
                return True
            ms = m.content.split()
            if len(ms) == 2:
                try:
                    X = list(map(int, ms[1].split(",")))
                except ValueError:
                    pass
                else:
                    if ms[0] in "fmr":
                        return all([x <= repeat for x in X])
            else:
                if ms[0] in "fmr":
                    return True

        print("awaiting for send reply")
        msg = await bot.wait_for("message", check=check)
        print("successfully recieved message")
        ms = msg.content.split()
        if len(ms) == 1:
            func_ids = [repeat - 1]
        else:
            func_ids = list(map(lambda x: int(x) - 1, ms[1].split(",")))

        return ms[0], func_ids

    lock = asyncio.Lock()
    async with lock:
        user_id = ctx.author.id
        srs = list(map(int, success_rate.split("x")))
        if len(srs) == 1:
            success_rate = srs[0]
            repeat = 1
        else:
            success_rate, repeat = srs
        target_results = [success_rate // i for i in range(1, 6)]
        target_results = list(map(lambda x: min(95, x), target_results))
        achievement_bonus_list = list(map(int, achievement_bonus.split(",")))
        for _ in range(repeat - len(achievement_bonus_list)):
            achievement_bonus_list.append(0)
        results = [0 for _ in range(repeat)]
        achievement = [0 for _ in range(repeat)]
        attempts_list = [0 for _ in range(repeat)]
        used_mp = 0
        reroll_number = 0
        modify_cost = 0
        reroll_cost = VariablesManager.reroll_cost[user_id]
        int_res_list = [0 for _ in range(repeat)]
        for r in range(repeat):
            result, attempts = dice_loop(
                attempts_list[r],
                results[r],
            )

            ach = achievement_bonus_list[r] + attempts
            if attempts >= 5:
                int_res = f"{r + 1}. {result} {ach}: highest"
            else:
                nxt_tgt = target_results[attempts]
                mod_cost = used_mp + max(result - nxt_tgt, 0)
                rrl_cost = used_mp + reroll_cost
                int_res = f"{r + 1}. {result} {ach} next: {nxt_tgt}\nfinish/reroll({rrl_cost})/modify({mod_cost})"
            results[r] = result
            achievement[r] = ach
            attempts_list[r] = attempts
            int_res_list[r] = int_res
        await send_multiple_message(VariablesManager.messages[user_id], ctx)
        VariablesManager.messages[user_id] = []
        fin = False
        fin = all([5 <= a for a in attempts_list])
        while not fin:
            await ctx.reply("\n".join(int_res_list))
            ms, func_ids = await interlude(
                repeat,
            )
            if ms == "f" or ms == "/roll":
                fin = True
            if not fin:
                for f in func_ids:
                    if attempts_list[f] == 5:
                        continue
                    if ms == "r":
                        used_mp += reroll_cost
                        reroll_number += 1
                    elif ms == "m":
                        result = results[f]
                        attempts = attempts_list[f]
                        next_target = target_results[attempts]
                        used_mp += max(result - next_target, 0)
                        modify_cost += max(result - next_target, 0)
                        results[f] = target_results[attempts]
                        attempts_list[f] += 1
                        VariablesManager.messages[user_id].append(
                            f"1d100({target_results[attempts]}%)->{result}->{results[f]} {achievement[f] + 1}"
                        )

                    result, attempts = dice_loop(attempts_list[f], results[f])
                    ach = achievement_bonus_list[f] + attempts
                    results[f] = result
                    achievement[f] = ach
                    attempts_list[f] = attempts
                for r in range(repeat):
                    if attempts_list[r] >= 5:
                        int_res = f"{r + 1}. {results[r]} {achievement[r]}: highest"
                    else:
                        nxt_tgt = target_results[attempts_list[r]]
                        int_res = f"{r + 1}. {results[r]} {achievement[r]} next: {nxt_tgt}\nfinish/reroll({used_mp + reroll_cost})/modify({used_mp + max(results[r] - nxt_tgt, 0)})"
                    int_res_list[r] = int_res
                fin = all([5 <= a for a in attempts_list])
                if VariablesManager.messages[user_id]:
                    await send_multiple_message(VariablesManager.messages[user_id], ctx)
                VariablesManager.messages[user_id] = []
        result = f"{achievement} reroll x{reroll_number} & modified:{modify_cost}-> used mp:{used_mp} "
        await ctx.reply(result)


@bot.command()
async def r_cost(ctx, cost):
    cost = int(cost)
    cost_before = VariablesManager.reroll_cost[ctx.author.id]
    VariablesManager.reroll_cost[ctx.author.id] = cost
    await ctx.send(f"reroll cost changed to {cost_before}->{cost}")


def dice_loop(
    user_id,
    target_results,
    attempts,
    result,
):
    while True:
        if attempts >= 5:
            break
        success_rate = target_results[attempts]
        result = random.randint(1, 100)

        if result <= success_rate:
            VariablesManager.messages[user_id].append(
                f"1d100({success_rate}%)->{result}"
            )
            attempts += 1
            continue
        else:
            VariablesManager.messages[user_id].append(
                f"1d100({success_rate}%)->{result}: Failure"
            )
            break
    return result, attempts


class DiceBotView(View):
    def __init__(self, user_id, rate, repeat, bonus_list):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.rate = rate
        self.target_results = [min(rate // i, 95) for i in range(1, 6)]
        self.repeat = repeat
        self.bonus_list = bonus_list
        self.results = [0 for _ in range(repeat)]
        self.achievement = [0 for _ in range(repeat)]
        self.attempts_list = [0 for _ in range(repeat)]
        self.reroll_cost = VariablesManager.reroll_cost[user_id]
        self.used_mp = 0
        self.reroll_number = 0
        self.int_res_list = [0 for _ in range(repeat)]
        self.fin = False
        self.ms = ""
        self.func_ids = []
        self.dice_log = []

    @discord.ui.button(label="Reroll", style=discord.ButtonStyle.primary)
    async def reroll(self, interaction: discord.Interaction, button: Button):
        interaction_user_id = interaction.user.id
        if interaction_user_id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return
        self.used_mp += self.reroll_cost
        self.reroll_number += 1
        if self.fin_check():
            self.on_timeout(interaction)
        if VariablesManager.messages[interaction.user.id]:
            await interaction.response.edit_message(
                "\n".join(VariablesManager.messages[interaction.user.id])
            )

    @discord.ui.button(label="Modify", style=discord.ButtonStyle.secondary)
    async def modify(self, interaction: discord.Interaction, button: Button):
        interaction_user_id = interaction.user.id
        if interaction_user_id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return
        for f in self.func_ids:
            if self.attempts_list[f] == 5:
                continue
            result = self.results[f]
            attempts = self.attempts_list[f]
            next_target = self.target_results[attempts]
            self.used_mp += max(result - next_target, 0)
            self.modify_cost += max(result - next_target, 0)
            self.results[f] = self.target_results[attempts]
            self.attempts_list[f] += 1
            VariablesManager.messages[interaction.user.id].append(
                f"1d100({self.target_results[attempts]}%)->{result}->{self.results[f]} {self.achievement[f] + 1}"
            )
        if self.fin_check():
            self.on_timeout(interaction)
        if VariablesManager.messages[interaction.user.id]:
            await interaction.response.edit_message(
                "\n".join(VariablesManager.messages[interaction.user.id])
            )
        VariablesManager.messages[interaction.user.id] = []

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.danger)
    async def finish(self, interaction: discord.Interaction, button: Button):
        interaction_user_id = interaction.user.id
        if interaction_user_id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return
        self.on_timeout(interaction)

    def fin_check(self):
        return all([5 <= a for a in self.attempts_list])

    async def on_timeout(self, interaction: discord.Interaction):
        result = f"{self.achievement} reroll x{self.reroll_number} & modified:{self.modify_cost}-> used mp:{self.used_mp} "
        VariablesManager.messages[self.user_id].append(result)
        await interaction.response.edit_message(
            "\n".join(VariablesManager.messages[interaction.user.id])
        )
        VariablesManager.messages[interaction.user.id] = []
        self.stop()

    def common_loop(self):
        for f in self.func_ids:
            if self.attempts_list[f] == 5:
                continue
            result, attempts = dice_loop(self.attempts_list[f], self.results[f])
            ach = self.bonus_list[f] + attempts
            self.results[f] = result
            self.achievement[f] = ach
            self.attempts_list[f] = attempts
        for r in range(self.repeat):
            if self.attempts_list[r] >= 5:
                int_res = f"{r + 1}. {self.results[r]} {self.achievement[r]}: highest"
            else:
                nxt_tgt = self.target_results[self.attempts_list[r]]
                int_res = f"{r + 1}. {self.results[r]} {self.achievement[r]} next: {nxt_tgt}\nfinish/reroll({self.used_mp + self.reroll_cost})/modify({self.used_mp + max(self.results[r] - nxt_tgt, 0)})"
            self.int_res_list[r] = int_res


@bot.tree.command(name="roll_command", description="行為判定を行う。")
@app_commands.describe(
    rate="成功率 (例: 135)",
    repeat="行為回数 (例: 3)",
    bonus="達成度ボーナス (例: 2,2,1)",
)
# 仮実装
async def roll_command(
    interaction: discord.Interaction, rate: int, repeat: int = 1, bonus: str = "0"
):
    bonus_list = list(map(int, bonus.split(",")))
    for _ in range(repeat - len(bonus_list)):
        bonus_list.append(0)
    view = DiceBotView(interaction.user.id, rate, repeat, bonus_list)
    for r in range(repeat):
        result, attempts = dice_loop(
            interaction.user.id,
            view.target_results,
            view.attempts_list[r],
            view.results[r],
        )

        ach = view.bonus_list[r] + attempts
        if attempts >= 5:
            int_res = f"{r + 1}. {result} {ach}: highest"
        else:
            nxt_tgt = view.target_results[attempts]
            mod_cost = view.used_mp + max(result - nxt_tgt, 0)
            rrl_cost = view.used_mp + view.reroll_cost
            int_res = f"{r + 1}. {result} {ach} next: {nxt_tgt}\nfinish/reroll({rrl_cost})/modify({mod_cost})"
        view.results[r] = result
        view.achievement[r] = ach
        view.attempts_list[r] = attempts
        view.int_res_list[r] = int_res
    await interaction.response.send_message(
        "\n".join(VariablesManager.messages[interaction.user.id]), view=view
    )


if __name__ == "__main__":
    bot.setup_hook = setup_hook
    bot.run(TOKEN)
