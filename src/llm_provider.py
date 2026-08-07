from litellm import completion


def ask_llm(
    provider,
    api_key,
    prompt,
    model=None
):

    models = {

        "OpenAI": "gpt-5-mini",

        "Anthropic": "claude-sonnet-4",

        "Google Gemini": "gemini/gemini-2.5-flash",

        "Groq": "groq/llama-3.3-70b-versatile",

        "OpenRouter": "openrouter/openai/gpt-5-mini"
    }


    if model is None:
        model = models[provider]


    response = completion(

        model=model,

        api_key=api_key,

        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]

    )


    return response.choices[0].message.content
