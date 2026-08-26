# Bot Mente Digna — Gerador de Cards

Bot Telegram para transformar frases em cards no padrão visual da Mente Digna.

## O que já faz

- Recebe imagem com frase.
- Usa visão multimodal para extrair somente o texto principal.
- Mostra o texto para conferência.
- Botão **GERAR CARD**.
- Botão **EDITAR TEXTO**.
- Gera PNG 1080x1350.
- Fundo branco.
- Texto preto e pesado.
- Aspas vermelhas obrigatórias por padrão.
- `@mentedigna` no canto inferior esquerdo.
- Caixa alta por padrão.
- Menu `/config`.
- Geração opcional de legenda.
- Pode receber texto digitado diretamente.

## 1. Criar o bot no Telegram

Abra o BotFather e crie um bot. Copie o token.

## 2. Criar a chave da API

Crie uma API key na OpenAI Platform. O projeto usa a Responses API para leitura de imagens e geração de legendas.

## 3. Configurar

Copie `.env.example` para `.env`:

```bash
cp .env.example .env
```

Preencha:

```text
BOT_TOKEN=...
OPENAI_API_KEY=...
```

Para restringir o bot somente à sua conta, coloque seu ID do Telegram em `ADMIN_USER_ID`.

## 4. Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

No Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

## 5. Docker

```bash
docker build -t mente-digna-bot .
docker run --env-file .env mente-digna-bot
```

## Padrão visual

O renderizador é determinístico. A IA não desenha o card. Ela somente lê a frase.

Isso é proposital: o layout fica consistente em todos os posts.

Para alterar o visual, edite `DEFAULT_CONFIG` em `bot.py` ou `renderer.py`.

## Observação

A chave da API e o token do Telegram nunca devem ser enviados para outras pessoas nem publicados no GitHub.
