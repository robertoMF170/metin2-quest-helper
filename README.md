# MT2Guide — Metin2 Quest Helper

> Fase final — correção de bugs (beta fechado)

Quest helper **100% client-side** (estilo RestedXP) para o cliente Gameforge Metin2 — **qualquer região oficial** (TR, EU, ...), a correr via **eXLib.mix**: guia de missões passo-a-passo com avanço automático, seta 3D, mira vermelha nos mobs e sincronização com o estado real das quests. Tu jogas; o guia aponta.

## O que faz

- Janela com a lista de missões e **passo-a-passo** (feito / atual / futuro)
- **Avanço automático** dos passos: `kill` conta mortes sozinho, `talk/turnin` avança no diálogo do NPC, `goto` ao chegar ao destino (collect/texto usam botão +1)
- **Seta no ecrã** que roda para o destino + distância em metros
- **Zona de spawn** dos mobs (centroides oficiais por reino nos mapas 1/2)
- **Mira vermelha** sobre cada mob que a missão manda matar (anel + cruz) + contador real ("Cachorro 3/10") no mob mais próximo — com fallback sem miras se o cliente não projetar instâncias
- **Missões de caça** (AVLANMA GÖREVİ): as 118 missões da wiki oficial (Lv2→Lv119), escolha entre 2 mobs detetada automaticamente (alvo, 1ª morte) ou botões Op.1/Op.2, com pesquisa por nome do mob
- Trava de alvo no mob certo + apontador 3D
- Estado gravado entre sessões (`quest_state.txt`, gerado em runtime)

## Requisitos

- Cliente Gameforge Metin2 — qualquer região oficial (TR, EU, ...) — com `eXLib.mix` compatível
- Windows

## Instalação

```bat
git clone https://github.com/robertoMF170/metin2-quest-helper-tr-tr.git
cd metin2-quest-helper-tr-tr
instalar-guia.bat        :: pergunta a pasta do jogo (onde esta o metin2client.exe)
```

O instalador copia `MT2Guide\` para a pasta do jogo, guarda o `init.py` atual como `init_bots.py` e instala o `init_guide.py`. Depois: `Jogar-Guia.bat` (ou abre o `metin2client.exe`) — o guia abre sozinho no mundo.

> Voltar aos bots: copiar `init_bots.py` de volta para `init.py`.

## Comandos no chat

| Comando | Efeito |
|---|---|
| `.g` | abre/fecha o guia |
| `.q` | quest line (seletor de missões) |
| `.qdiag` | diagnóstico do passo atual → `syserr_guide.txt` |
| `.qkey` | trace de teclas 60s (debug) |
| `.qpos` | grava posição em `Data\posicoes.txt` |
| `.qstate` | estado real das quests da conta para o log |
| `.qdump` | dump das APIs quest/event/eXLib |

Teclas: `INSERT`/`F7` guia · `N`/`F8` quest line.

## Estrutura

```
init_guide.py                    loader (fase BOOTSTRAP + fase LOADER)
MT2Guide/__init__.py             módulo principal do guia
MT2Guide/Modules/GuideData.py    base de dados de missões
MT2Guide/Modules/GuideDialog.py  avanço por diálogo NPC
MT2Guide/Modules/GuideNav.py     seta/anéis 3D + trilha
MT2Guide/Modules/GuideMark.py    miras sobre os mobs
MT2Guide/Modules/GuideQuestSync.py  sync com o estado real das quests
MT2Guide/Modules/GuideUI.py      janelas do guia
MT2Guide/Modules/GuideLib.py     hooks + plumbing eXLib
MT2Guide/Data/quests_*.txt       bases de dados (wiki, caça, premium, yohara, extra)
instalar-guia.bat / Jogar-Guia.bat
```

## Fase atual

**Beta fechado / fase final** — a corrigir os últimos bugs antes de release público. Encontra um bug? Abre uma issue com o `syserr_guide.txt`.

## Créditos

- **eXLib** — loader `.mix` da comunidade Metin2; o MT2Guide corre em cima dele. O eXLib original não é meu.
- Dados de missões: wiki oficial Metin2 (`quests_wiki.txt`, `quests_caca.txt`).

## Nota de privacidade

Este repo contém apenas código + bases de dados de missões. Ficheiros gerados em runtime pelo jogo (`quest_state.txt`, `quests_gravadas.txt`, `api_dump_quest.txt`, `mobs_vnum.txt`, `posicoes.txt`, `dead_zones.txt`) ficam **fora do git** (ver `.gitignore`).
