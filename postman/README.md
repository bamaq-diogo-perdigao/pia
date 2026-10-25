# Simulação local: ferramenta de imagens do chat

O contrato vem de src/HTTPServer.py: POST /v1/images/generations aceita prompt, n e response_format e retorna created/data com b64_json. A simulação responde com um PNG sintético e também modela erro 503; rotas não modeladas retornam 501.

mocks/pia-images/default.js implementa somente essa dependência. O código testado é o cliente real src/chat_tools.py, fora da simulação. simulations/chat-images.sim.yaml reúne a dependência em /pia. Rode tests/simulate_chat_images.py com o Python da PIA para iniciar, verificar os requests no log NDJSON e encerrar a simulação automaticamente. Não requer publicação ou alteração em workspace compartilhado.
