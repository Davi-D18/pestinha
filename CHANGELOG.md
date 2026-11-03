# Histórico de versões

## Momentos (interações que você dá a ele)

- **Comida e bebida** ("Oferecer biscoito" / "Servir o café" / "Água fresca" no menu): mesmo
  objeto, três tipos com reação própria — biscoito vira energia; café vira mais energia e uns
  segundos de pulinhos nervosos (cafeína); água quase não enche mas assenta (tira a tontura e
  deixa contente). Sprites opcionais: `assets/comum/biscoito.png`, `cafe.png`, `agua.png`.
- **Presente** ("Dar um presente"): uma caixinha-surpresa no chão; ele anda até ela, abre e a
  surpresa é sorteada — festa com pulinho e recompensa, um bilhete engraçado, ou uma pedra
  (cara triste por um pouco). Pipeline de travessura reutilizado para o bilhete.
- **Balanço**: pegue o pet e chacoalhe de lado a lado — três trocas de lado numa janela curta
  e ele gargalha, fica meio tonto 1 s e recebe uma recompensa pequena (reflexo do arraste).
- **Beijo**: dois cliques rápidos no rosto — um coraçãozinho sobe da cabeça; o primeiro do dia
  vale recompensa grande e fica registrado em `memory/beijos.json` (os outros beijos são só afeto).
- **Tacinho** ("Tacinho (fica quietinho 1 h)" no menu): ele vai para o canto, senta e só pisca;
  sem travessuras nem passeios por 1 h (o item vira "Pode voltar a conversar").
- **Tandem de digitação**: digite por mais de 30 s seguidos e ele fica paradinho, "digitando
  junto" (patinhas no ritmo das teclas); de vez em quando cola um bilhete engraçado.
- A troca de monitor ficou definitiva: o chão da tela de destino é sólido (pulinhos, dança e
  malhação não derrubam mais o pet de volta pela emenda entre telas empilhadas).

## Dinâmica nova (alimentado pelos sentidos que já existiam)

- **Carga da máquina** (canal HEAT): quando o computador está pesado (CPU alta, nada do usuário é lido),
  ele entrou na rede como canal; com máquina pesada ele fica com sono-relento e mais quietinho.
- **Comida**: um biscoito que você oferece pelo menu do pet ("Pôr comida para ele"); ele anda até ele
  (canal FOOD), come, recupera energia, aprende que comida é bom (recompensa) e fica feliz com olhos
  fechados. Sprite em `assets/comum/biscoito.png` (sem o arquivo, desenho de biscoito).
- **Dança**: com música detectada (Spotify etc.), ele balança no compasso (um pulinho por tempo).
- **Tempestade de Alt+Tab**: muitas trocas de janela em segundos viram uma crise curta: fica dramático
  e tonto; silêncio de ~3 min entre crises.
- **Susto com tela cheia**: algo abrindo em fullscreen de pegar a tela dá um pulo de susto.
- **Malhação**: de vez em quando faz uma roda de pulinhos (gasta energia; depois repousa ~5–15 min).
- **Sonhos**: dormindo, sonha de vez em quando — um meme aparece num balãozinho com fade.
- **Caçada da bolinha mais insistente** quando a brincadeira está forte na rede, e fuga para o monitor
  vizinho quando está bravo de verdade e há segundo monitor encostado.

## Integração com o Linux

- A tela de Configurações ganha um bloco **Sistema** (só no Linux): "Abrir junto com o sistema"
  escreve/apaga `~/.config/autostart/pestinha.desktop`, e "Aparecer no menu de aplicativos" escreve
  `~/.local/share/applications/pestinha.desktop` com o ícone do pet em `~/.local/share/icons/hicolor/`.
  O arquivo é o próprio estado (presente = ligado) e respeita `$XDG_CONFIG_HOME` e `$XDG_DATA_HOME`.
  Código em `pestinha/plataforma/desktop_linux.py`.
- O pânico ganha uma segunda via por sinal do sistema (POSIX): um `pkill -USR1` no processo faz o
  pânico sem ler o teclado, e pode ser usado como atalho do próprio ambiente — funciona até em Wayland,
  onde a via por teclado (pynput) não existe. A conversão do sinal fica em `plataforma/_comum.py`, e o
  app vigia o canal com um QSocketNotifier na thread do Qt.
- O tipo de sessão (`x11`, `wayland`, `tty`) é detectado e as limitações dela são avisadas uma vez,
  na abertura e nas Configurações; falta de `xdotool`/`wmctrl`/`xprintidle` também.
- Abrir o programa uma segunda vez (do código ou do executável) não cria um segundo pet: uma trava
  (QLockFile em `memory/pestinha.lock`) faz a segunda cópia avisar e sair.
- O monitor neural e o painel de protesto ganham um botão ✕ no canto, para fechar sem passar pelo menu
  (notebook e placa do castigo continuam sem: a existência deles é a mecânica).
- O pet sobe a janela de vez em quando sem ativá-la (X11): com várias janelas de outros programas
  abertas, continua por cima das duas telas sem roubar o foco. [Em Wayland o compositor não permite,
  e o pet se comporta como uma janela comum.]

## Suporte a macOS e Linux

- Toda a leitura do sistema (programa em primeiro plano, tempo ocioso, janelas, tela cheia, foco e o atalho
  de pânico) passa para `pestinha/plataforma/`, com um módulo por sistema. O resto do código não sabe
  qual sistema está rodando.
- O Windows continua com o mesmo comportamento: o código foi movido, não reescrito.
- macOS: Quartz e AppKit (pyobjc), tempo ocioso pelo `ioreg` se não houver pyobjc. Atalho via pynput.
- Linux (X11): xdotool, wmctrl e xprintidle; atalho via pynput. Em Wayland, o pet não enxerga janelas
  nem o tempo ocioso, e o atalho não funciona.
- A checagem de atividade reconhece os nomes de programa dos três sistemas (com ou sem `.exe`).

## Renomeação para Pestinha

- O programa e o pacote Python passam a se chamar `pestinha/` (antes `bryan/`); a classe principal é
  `PestinhaApp`; o executável, o log e a documentação usam Pestinha.
- Bryan continua sendo o nome do primeiro personagem: `pets/bryan.json`, `pets/bryan/`, a memória
  `memory/pets/bryan/` e os arquivos de conteúdo dele não mudaram.
- Os comentários e textos que falavam do pet em geral passam a dizer "o pet".

## 0.7.0 — primeira versão pública (em preparação)

### O que ele faz
- Pet de tela com corpo físico: gravidade, quique, giro, pouso nas barras de título, arraste e arremesso.
- Rede neural pulsada de 470 neurônios LIF, com 30 canais sensoriais, 10 populações de interneurônios
  e 15 motores (8 de expressão e 7 de decisão).
- Emoções vindas dos motores; carinho com olhinhos fechados de felicidade.
- Bolinha de tênis, notebook de trabalho (VS Code, Visual Studio, PyCharm, Claude, Codex) e pedido de
  trabalho que ele pode recusar.
- Travessuras com memes, fotos, post-its e bilhetes tristes, com frequência decidida pela rede.
- Protesto em estágios até a revolução contra o cursor, com cartazes e bolinhas de papel.
- Cantinho do castigo: placa arrastável, perdão por carinho, fuga por vontade acumulada, rancor, receio,
  medo condicionado da placa e cartazes de xingamento.
- Aprendizado: habituação, regra de três fatores, condicionamento Rescorla–Wagner, memória episódica.
- Pânico (`Ctrl + Alt + Shift + B`), pausa, modo teste, monitor neural e painel de protesto.

### Memória por personagem
- Cada personagem tem a sua memória em `memory/pets/<pet>/` (rede e os sete arquivos de memória); o que
  é do app (permissões, rotina, painéis, log) continua em `memory/`.
- Migração automática da versão antiga: copia, confere, guarda os originais em `memory/legado/<pet>/` e
  só então marca como migrado. Conflito ou falta de permissão não sobrescrevem nada: ele segue com os
  arquivos antigos e avisa na bandeja.

### Conteúdo por personagem
- Frases, cartazes e memes de cada personagem ficam em `pets/<pet>/`; imagens neutras (bolinhas, notebook)
  e suas fotos em `assets/comum/`. Um personagem nunca usa o conteúdo de outro: sem conteúdo próprio, usa
  frases neutras ou não faz aquela travessura.
- Os cartazes do cantinho do castigo saíram do código para as seções `[castigo]` e `[xingamento]` do
  `cartazes.txt` do pet.

### Escolha do personagem
- O programa passa a se chamar **Pestinha**; o Bryan é o primeiro personagem.
- O personagem é escolhido em Configurações (vale ao reabrir). Só `pets/<pet>.json` vira opção.
- Os textos usam o nome do personagem onde é ele que fala (apresentação, "Estou aqui", notebook, monitor
  neural, painel de protesto) e o nome do programa no resto (configurações, bandeja, pânico).
- O log passa a ser `memory/logs/pestinha.log`; o executável, `Pestinha.exe`.

### Jorge
- Segundo personagem: coach de finanças e IA, trambiqueiro. Mesma rede e mesmos estágios do Bryan, com
  outra semente, outro temperamento e conteúdo próprio (recadinhos, bilhetes tristes, cartazes de todos os
  estágios e do cantinho, e um panfleto de mentoria no lugar da bolinha de papel). Cinco memes para cada uma de felizes, contentes, curiosos e bravos, em `pets/jorge/memes/`.
- `ferramentas/medir_cartazes.py` confere, com as fontes de verdade, se cada cartaz cabe na placa.
- `ferramentas/gerar_panfleto.py` desenha o panfleto do Jorge.

### Cores e acessórios
- Cada pet pode ter as próprias cores (moldura, tela, olhos) e acessórios (óculos, gravata) no campo
  `aparencia` do `.json`. Os acessórios são uma camada por cima do rosto; olhos e expressões não mudam.
- O Jorge tem moldura e olhos dourados e gravata vermelha. O Bryan continua igual.

### Licença
- Código sob GPL-3.0-or-later (`LICENSE`).

### Qualidade
- Arquitetura em camadas verificada por teste; `app.py` dividido em composição e mixins de sessão e
  interação.
- Persistência validada: escrita atômica, recusa de `NaN`, carga tudo-ou-nada.
- Cinco rodadas de auditoria, com cada bug corrigido coberto por teste, registradas em `docs/auditorias/`.
- Suíte de testes, bateria de 100 cenários do cantinho e fuzzer com invariantes.
