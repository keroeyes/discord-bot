import discord
from openai import OpenAI

# 본인의 API 키 입력
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# OpenAI 클라이언트 생성
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 디스코드 클라이언트 설정
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'봇이 준비됐어요! {client.user}')

@client.event
async def on_message(message):
    # 봇 본인이 보낸 메시지는 무시
    if message.author == client.user:
        return

    # !질문으로 시작하는 메시지 처리
    if message.content.startswith('!질문'):
        # 질문 내용 가져오기
        user_input = message.content[len('!질문 '):].strip()

        if not user_input:
            await message.channel.send('질문을 입력해주세요! 예: `!질문 디스코드 봇은 어떻게 만들어?`')
            return

        try:
            # OpenAI API 호출
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": user_input}
                ]
            )

            # 답변 추출 및 전송
            answer = response.choices[0].message.content
            await message.channel.send(answer)

        except Exception as e:
            await message.channel.send(f'🚨 오류가 발생했어요: {e}')

client.run(DISCORD_TOKEN)
