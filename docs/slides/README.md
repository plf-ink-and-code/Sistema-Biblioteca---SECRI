# Apresentação — Como usar o sistema

Material para apresentar o sistema a um público não-técnico (bibliotecários, equipe).

## Arquivos

- `index.html` — apresentação de slides (reveal.js). Abre no navegador.
- `Biblioteca-SECRI-como-usar.pdf` — a mesma apresentação em PDF (para imprimir,
  compartilhar ou apresentar sem internet).
- `img/` — capturas de tela do sistema usadas nos slides.

## Como abrir os slides

Abra o `index.html` no navegador. Se as imagens não carregarem via `file://`,
sirva a pasta numa porta, por exemplo:

```bash
python3 -m http.server 8090 --directory docs/slides
# depois acesse http://localhost:8090
```

Durante a apresentação:

- **← →** navegam entre os slides
- **F** entra em tela cheia
- **Esc** mostra todos os slides
- **S** abre as notas do apresentador (janela separada)

> O `index.html` usa reveal.js via CDN, então precisa de internet para abrir os
> slides. Sem internet, use o **PDF**.
