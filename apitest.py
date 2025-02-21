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



# from openai import OpenAI

# client = OpenAI(
#   api_key="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"
# )

# completion = client.chat.completions.create(
#   model="gpt-4o-mini",
#   store=True,
#   messages=[
#     {"role": "user", "content": "write a haiku about ai"}
#   ]
# )

# print(completion.choices[0].message);
