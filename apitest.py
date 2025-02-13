import openai

# Replace with your OpenAI API key
client = openai.OpenAI(api_key="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")

try:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello!"}]
    )
    print("API key is valid. Response:", response.choices[0].message.content)
except openai.AuthenticationError:
    print("Invalid API key!")
except Exception as e:
    print("Error:", e)
