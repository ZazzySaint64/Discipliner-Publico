# Assets do Focum

Salve os PNGs aqui, com estes nomes exatos (o app já procura por eles nesses
caminhos — assim que o arquivo existir, aparece sozinho, sem precisar mexer em código):

| Arquivo | Onde aparece | Desbloqueio |
|---|---|---|
| `focum_idle.png` | Foto de perfil padrão | sempre disponível |
| `focum_sleeping.png` | Histórico vazio (nenhuma missão concluída ainda) + foto de perfil | conquista "Disciplina de Ferro" (30 dias de sequência) |
| `focum_thumbsup.png` | Foto de perfil | conquista "Uma Semana Forte" (7 dias de sequência) |
| `focum_writing.png` | Foto de perfil | conquista "Aquecendo" (10 missões concluídas) |
| `focum_meditating.png` | Foto de perfil | conquista "Nível 5" |
| `focum_walking.png` | Foto de perfil | conquista "Duas Semanas Fortes" (14 dias de sequência) |
| `focum_celebrating.png` | Foto de perfil | conquista "Cem Dias" (100 dias de sequência) |
| `focum_studying.png` | Foto de perfil | conquista "Lenda" (100 missões concluídas) |
| `focum_star.png` | Foto de perfil | conquista "Nível 15" |

Fundo transparente ou sólido tanto faz — o app corta em quadrado e centraliza.
Qualquer resolução serve (o app redimensiona), mas quanto maior melhor.

Se faltar algum arquivo, o app não quebra — só não mostra aquele estado
específico (ex.: histórico vazio sem `focum_sleeping.png` fica só com o texto,
sem a imagem).

## Regerar a partir da arte bruta

Os 9 PNGs acima saem de uma folha de sprites 5x3 em `raw/` — recorte,
remoção do xadrez de transparência e enquadramento por
`python scripts/gen_focum.py` (mexer no `POSE_MAP` de lá pra trocar qual
célula vira qual pose).

`focum_intro.gif` é a animação do ícone que toca na tela de abertura
(`ui.kv` > `Screen name:"splash"`). Sai de `raw/faça_um_vídeo_*.mp4` por
`python scripts/gen_intro_gif.py` (precisa de ffmpeg — `pip install
imageio-ffmpeg` resolve).
