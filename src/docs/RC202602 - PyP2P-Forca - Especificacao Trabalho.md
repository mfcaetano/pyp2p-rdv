# Trabalho de Programação — **Jogo da Forca P2P (PyP2P-Forca)**

## Sumário

- [Resumo](#resumo)
- [Arquitetura P2P: Conceitos e Papéis](#arquitetura-p2p-conceitos-e-papéis)
- [Objetivos](#objetivos)
- [Identidade e Escopo](#identidade-e-escopo)
- [Transporte e Codificação](#transporte-e-codificação)
- [Arquitetura da Solução](#arquitetura-da-solução)
  - [Duas camadas de conexão](#duas-camadas-de-conexão)
  - [Componentes de um peer](#componentes-de-um-peer)
  - [Ciclo de vida de uma partida](#ciclo-de-vida-de-uma-partida)
- [Protocolo Peer–Rendezvous](#protocolo-peerrendezvous)
  - [REGISTER](#register)
  - [DISCOVER](#discover)
  - [UNREGISTER](#unregister)
  - [Proteção contra abusos](#proteção-contra-abusos)
  - [Erros genéricos](#erros-genéricos)
- [Protocolo Peer–Peer](#protocolo-peerpeer)
  - [Envelope comum](#envelope-comum)
  - [Mensagens de sessão](#mensagens-de-sessão)
    - [HELLO / HELLO_OK](#hello--hello_ok)
    - [PING / PONG](#ping--pong)
    - [BYE / BYE_OK](#bye--bye_ok)
    - [ERROR](#error)
  - [Mensagens de lobby](#mensagens-de-lobby)
    - [GAME_LIST / GAME_LIST_OK](#game_list--game_list_ok)
    - [JOIN / JOIN_OK / JOIN_ERR](#join--join_ok--join_err)
    - [LEAVE / LEAVE_OK](#leave--leave_ok)
  - [Mensagens de partida](#mensagens-de-partida)
    - [GAME_START](#game_start)
    - [STATE](#state)
    - [GUESS / GUESS_RESULT](#guess--guess_result)
    - [GAME_OVER](#game_over)
  - [Regras do jogo](#regras-do-jogo)
  - [Máquina de estados](#máquina-de-estados)
  - [Tratamento de falhas](#tratamento-de-falhas)
- [Gerenciamento de Conexões e Reconexões](#gerenciamento-de-conexões-e-reconexões)
- [Interface de Usuário (CLI)](#interface-de-usuário-cli)
- [Arquivo de configuração](#arquivo-de-configuração)
- [Arquitetura de Módulos](#arquitetura-de-módulos)
- [Observabilidade e Logs](#observabilidade-e-logs)
- [Material Disponibilizado](#material-disponibilizado)
- [Critérios de Avaliação](#critérios-de-avaliação)
- [Cenários de Teste Mínimos](#cenários-de-teste-mínimos)
- [Exemplo Completo de Sessão](#exemplo-completo-de-sessão)

---

## Resumo

Este trabalho consiste na implementação de um **cliente P2P de Jogo da Forca** que:

- Registra-se em um **servidor Rendezvous** e descobre outros peers de forma recorrente e automática;
- Mantém **conexões TCP persistentes** com os peers descobertos (malha de descoberta);
- Permite que **qualquer peer crie uma partida** e passe a atuar como **host** (coordenador temporário);
- Permite que outros peers **descubram e entrem** em partidas abertas, formando uma **estrela de jogo** centrada no host;
- Conduz a partida por turnos, com o host mantendo o **estado autoritativo** e difundindo-o aos jogadores;
- Mantém sessões vivas com **PING/PONG** e as encerra de forma limpa com **BYE/BYE_OK**;
- Tolera a **saída inesperada de jogadores** e reage corretamente à **queda do host**.

Não há servidor de jogo central. O Rendezvous apenas registra e lista peers; toda a lógica do jogo roda nos próprios peers. **Não há relay nem múltiplos saltos**: cada peer comunica-se diretamente com os peers alcançáveis.

---

## Arquitetura P2P: Conceitos e Papéis

A **arquitetura peer-to-peer (P2P)** é um modelo de comunicação distribuída em que cada nó (*peer*) exerce simultaneamente as funções de cliente e servidor. Suas características principais — **descentralização, escalabilidade, resiliência, distribuição de recursos, heterogeneidade e dinamicidade (*churn*)** — impõem ao projetista a necessidade de mecanismos de descoberta de peers, tolerância a falhas e atualização dinâmica da topologia.

Neste trabalho, os papéis desempenhados pelos peers são:

1. **Peer de descoberta** — o servidor Rendezvous atua como ponto de encontro inicial. Como os peers entram e saem da rede de forma dinâmica, a descoberta contínua é essencial.
2. **Host de partida** — papel *temporário e rotativo*: qualquer peer pode assumi-lo ao criar uma partida. O host conhece a palavra secreta, valida jogadas, controla turnos e difunde o estado. Ao fim da partida, o papel se dissolve.
3. **Jogador** — peer que entrou em uma partida hospedada por outro. Envia palpites e exibe o estado recebido.
4. **Peer de observabilidade** — todo peer mede RTT e registra eventos de conexão e falha, informação que alimenta a decisão de reconexão.

O modelo resultante é um **P2P híbrido com coordenação eleita por partida** — o mesmo padrão de jogos multiplayer com "hospedagem por jogador". Ele mantém a simetria do P2P (não existe nó com papel fixo de servidor) e, ao mesmo tempo, expõe o estudante ao problema central de sistemas distribuídos: **manter estado consistente entre nós que podem falhar a qualquer momento**.

---

## Objetivos

1. Exercitar conceitos de **arquitetura P2P**, **protocolos de aplicação** e **programação com sockets TCP**;
2. Implementar um cliente P2P capaz de:
    - Registrar-se e descobrir peers via Rendezvous (`REGISTER` / `DISCOVER` / `UNREGISTER`);
    - Estabelecer e manter conexões TCP com peers acessíveis (`HELLO/HELLO_OK`, `PING/PONG`, `BYE/BYE_OK`);
    - Atuar como **host** e como **jogador** no mesmo programa;
    - Descobrir, criar e entrar em partidas (`GAME_LIST`, `JOIN`, `LEAVE`);
    - Conduzir uma partida completa por turnos (`GAME_START`, `STATE`, `GUESS`, `GAME_OVER`);
    - Reagir corretamente à saída de jogadores e à queda do host.

---

## Identidade e Escopo

Cada peer é identificado como `name@namespace`, por exemplo `alice@CIC`.

- **namespace**: agrupador lógico — funciona como a "sala" onde as partidas são anunciadas (ex.: `UnB`, `CIC`).
- **name**: identificador único dentro do namespace.
- **peer_id**: formado por `name@namespace`.
- **game_id**: identificador de uma partida, gerado pelo host. Formato: `<host_peer_id>/<8 caracteres hexadecimais>`, ex.: `alice@CIC/3f9a2c1b`. O prefixo garante unicidade global sem coordenação; o sufixo distingue partidas sucessivas do mesmo host.

**Restrição de escopo:** um peer participa de **no máximo uma partida por vez**, seja como host ou como jogador. Participação simultânea em múltiplas partidas é opcional (ver bônus).

---

## Transporte e Codificação

| Item | Valor |
|---|---|
| Transporte | TCP |
| Codificação | JSON UTF-8, um objeto por linha, delimitado por `\n` |
| Tamanho máximo de linha | 32 KiB (32768 bytes) |
| `ttl` | fixo em `1`, não decrementa |
| Keep-alive | `PING` a cada 30 s (configurável) |
| Timeout de PONG | 3 PINGs consecutivos sem PONG ⇒ conexão marcada `STALE` e fechada |
| Timeout de turno | 30 s (configurável) |
| Erro de leitura/escrita | conexão fechada imediatamente |

Toda mensagem — requisição ou resposta, para o Rendezvous ou para outro peer — é **um objeto JSON válido em uma única linha**. Linhas que não sejam JSON válido devem ser respondidas com `ERROR` (peer–peer) e a conexão fechada.

---

## Arquitetura da Solução

### Duas camadas de conexão

O sistema opera com duas camadas lógicas sobre as mesmas conexões TCP:

```
                        ┌──────────────────────┐
                        │  Servidor Rendezvous │
                        │  pyp2p.mfcaetano.cc  │
                        │       TCP/8080       │
                        └──────────┬───────────┘
              REGISTER / DISCOVER / UNREGISTER (conexões curtas)
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
   ┌────────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
   │   alice@CIC     │    │    bob@CIC      │    │   carol@CIC     │
   │   (HOST)        │    │   (jogador)     │    │   (jogador)     │
   └───┬─────────┬───┘    └───┬─────────┬───┘    └───┬─────────┬───┘
       │         │            │         │            │         │
       │         └╌╌╌╌╌╌╌╌╌╌╌╌┘         └╌╌╌╌╌╌╌╌╌╌╌╌┘         │
       │              malha de descoberta (HELLO, PING, GAME_LIST)
       │         ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ │
       │                                                        │
       └════════════════════ estrela da partida ════════════════┘
                   (JOIN, GAME_START, STATE, GUESS, GAME_OVER)
```

1. **Malha de descoberta** — cada peer conecta-se a **todos** os peers descobertos no seu namespace, faz o handshake `HELLO/HELLO_OK` e mantém a conexão com `PING/PONG`. É por essa malha que um peer descobre quais vizinhos hospedam partidas abertas (`GAME_LIST`).

2. **Estrela da partida** — quando um peer entra em uma partida, as mensagens de jogo trafegam **somente entre ele e o host**, pela conexão TCP já existente na malha. Jogadores **não trocam mensagens de jogo entre si**; o host é a única fonte do estado.

Consequência importante: **não se abre uma segunda conexão para o jogo**. A conexão da malha é reutilizada; o que muda é o conjunto de tipos de mensagem aceitos naquele contexto.

### Componentes de um peer

```
 ┌────────────────────────────────────────────────────────────────┐
 │                        P2PForcaApp                             │
 │────────────────────────────────────────────────────────────────│
 │  RendezvousClient  │ REGISTER / DISCOVER / REFRESH / UNREGISTER│
 │  PeerServer        │ aceita e abre conexões TCP; HELLO         │
 │  PeerTable         │ estado dos peers, RTT, backoff, STALE     │
 │  KeepAlive         │ PING / PONG periódico                     │
 │  GameHost          │ máquina de estados do host (0 ou 1 ativa) │
 │  GamePlayer        │ máquina de estados do jogador (0 ou 1)    │
 │  MessageRouter     │ despacha mensagens por tipo → módulo      │
 │  CLI               │ comandos do usuário                       │
 └────────────────────────────────────────────────────────────────┘
        │  tarefas periódicas (asyncio ou threads)
        ├── discover a cada N s → reconciliar PeerTable → conectar novos
        ├── refresh de registro antes do TTL expirar
        ├── keep-alive por conexão
        └── timeout de turno (somente no host, durante partida)
```

### Ciclo de vida de uma partida

```
  alice (host)                 bob (jogador)               carol (jogador)
      │                             │                             │
      │  /create banana             │                             │
      │  [partida OPEN]             │                             │
      │                             │  /games                     │
      │◄──────── GAME_LIST ─────────┤                             │
      ├──────── GAME_LIST_OK ──────►│                             │
      │                             │  /join alice@CIC            │
      │◄────────── JOIN ────────────┤                             │
      ├────────── JOIN_OK ─────────►│                             │
      │◄────────────────────────── JOIN ──────────────────────────┤
      ├────────────────────────── JOIN_OK ───────────────────────►│
      │  /start                     │                             │
      ├──────── GAME_START ────────►│                             │
      ├──────────────────────── GAME_START ──────────────────────►│
      ├──────── STATE seq=1 ───────►│  (vez de bob)               │
      ├────────────────────── STATE seq=1 ───────────────────────►│
      │◄──────── GUESS "a" ─────────┤                             │
      ├────── GUESS_RESULT ok ─────►│                             │
      ├──────── STATE seq=2 ───────►│  (vez de carol)             │
      ├────────────────────── STATE seq=2 ───────────────────────►│
      │◄─────────────────────── GUESS "n" ────────────────────────┤
      │            ...                                            │
      ├──────── GAME_OVER ─────────►│                             │
      ├──────────────────────── GAME_OVER ───────────────────────►│
      │  [partida FINISHED]         │                             │
```

---

## Protocolo Peer–Rendezvous

O servidor Rendezvous é o ponto de encontro dos peers. Ele **não participa do jogo**: apenas registra peers, lista peers e remove registros.

> Como plataforma de testes, utilize o servidor público disponível em **pyp2p.mfcaetano.cc** (IP 45.171.101.167), porta **TCP/8080**.
> A documentação de referência do servidor está em <https://github.com/mfcaetano/pyp2p-rdv>. Esta seção reproduz o protocolo na íntegra; em caso de divergência, prevalece a documentação do repositório.

**Modelo de conexão:** cada conexão TCP com o Rendezvous aceita **exatamente um comando** (uma linha JSON) e é encerrada pelo servidor após a resposta. O cliente deve, portanto, abrir uma conexão nova para cada operação.

**Formato:** cada mensagem é um objeto JSON em uma única linha terminada por `\n`. O servidor impõe limite de **32 KB por linha**. Linhas vazias geram erro.

**Regras gerais de resposta:**

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | string | `"OK"` em caso de sucesso; `"ERROR"` em caso de falha |
| `message` | string | Presente apenas quando `status == "ERROR"`; código do erro |

### REGISTER

Registra (ou atualiza) um peer no servidor. Também é usado para **renovar o TTL** (refresh) — basta reenviar o mesmo `REGISTER` antes de o registro expirar.

**Requisição:**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `type` | string | sim | `"REGISTER"` |
| `namespace` | string | sim | 1 a 64 caracteres |
| `name` | string | sim | 1 a 64 caracteres |
| `port` | inteiro | sim | Porta TCP em que o peer aceita conexões (1–65535) |
| `ttl` | inteiro | não | Tempo de vida do registro em segundos (1–86400). Padrão: 7200 |

```json
{ "type": "REGISTER", "namespace": "CIC", "name": "alice", "port": 8081, "ttl": 3600 }
```

**Resposta de sucesso:**

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | string | `"OK"` |
| `ttl` | inteiro | TTL efetivamente aplicado (após saturação em 1–86400) |
| `ip` | string | Endereço IP **observado pelo servidor** — é o IP público do peer, que será divulgado aos demais via `DISCOVER` |
| `port` | inteiro | Porta registrada |

```json
{ "status": "OK", "ttl": 3600, "ip": "45.171.103.246", "port": 8081 }
```

> **Importante:** o campo `ip` da resposta é a única forma de o peer conhecer seu endereço público. Peers atrás de NAT recebem aqui o IP do roteador, e conexões de entrada só funcionarão se a porta estiver encaminhada. Esse é um comportamento esperado em redes P2P reais e deve ser registrado nos logs.

**Erros possíveis:**

| `message` | Causa |
|---|---|
| `bad_name` | `name` ausente, vazio ou com mais de 64 caracteres |
| `bad_namespace` | `namespace` ausente, vazio ou com mais de 64 caracteres |
| `bad_port` | `port` não inteiro ou fora de 1–65535 |
| `bad_ttl` | `ttl` presente e não inteiro (valores fora da faixa são saturados, não geram erro) |

```json
{ "status": "ERROR", "message": "bad_port" }
```

### DISCOVER

Retorna a lista de peers registrados. O servidor **só responde a peers com registro válido** (mesmo IP de um registro não expirado).

**Requisição:**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `type` | string | sim | `"DISCOVER"` |
| `namespace` | string | não | Se omitido, retorna peers de todos os namespaces; se inexistente, retorna lista vazia |

```json
{ "type": "DISCOVER", "namespace": "CIC" }
```

**Resposta de sucesso:**

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | string | `"OK"` |
| `peers` | lista | Um objeto por peer registrado (pode ser vazia) |
| `peers[].ip` | string | IP público do peer |
| `peers[].port` | inteiro | Porta de escuta do peer |
| `peers[].name` | string | Nome do peer |
| `peers[].namespace` | string | Namespace do peer |
| `peers[].ttl` | inteiro | TTL configurado no registro |
| `peers[].expires_in` | inteiro | Segundos restantes até a expiração |

```json
{
  "status": "OK",
  "peers": [
    { "ip": "45.171.103.246", "port": 8081, "name": "alice", "namespace": "CIC", "ttl": 3600, "expires_in": 3527 },
    { "ip": "45.171.101.167", "port": 8082, "name": "bob",   "namespace": "CIC", "ttl": 7200, "expires_in": 5908 }
  ]
}
```

> **Nota:** a resposta **inclui o próprio peer** que fez a consulta. O cliente deve filtrá-lo pelo par (`name`, `namespace`) antes de tentar conectar-se a si mesmo.

**Erros possíveis:**

| `message` | Causa |
|---|---|
| `bad_namespace` | `namespace` presente com tamanho inválido |
| `peer_not_registered` | O IP de origem não possui registro válido |

### UNREGISTER

Remove o registro do peer. Deve ser enviado no encerramento limpo da aplicação.

**Requisição:**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `type` | string | sim | `"UNREGISTER"` |
| `namespace` | string | sim | Namespace do registro |
| `name` | string | não | Se presente, deve coincidir com o registro |
| `port` | inteiro | não | Se presente, deve coincidir com o registro |

```json
{ "type": "UNREGISTER", "namespace": "CIC", "name": "alice", "port": 8081 }
```

**Resposta de sucesso:**

```json
{ "status": "OK" }
```

**Erros possíveis:**

| `message` | Causa |
|---|---|
| `namespace_required` | Campo `namespace` ausente |
| `bad_namespace` | `namespace` com tamanho inválido |
| `bad_port (<valor>)` | `port` não inteiro ou fora de 1–65535 |
| `peer_not_registered` | O IP de origem não possui registro válido |
| `peer_credentials_do_not_match` | IP de origem, `namespace`, `name` ou `port` divergem do registro |

> **Dica:** use `DISCOVER` para inspecionar os dados registrados do seu peer ao depurar `peer_credentials_do_not_match`.

### Proteção contra abusos

- **Limite de taxa:** cada IP pode enviar **50 requisições por minuto**. Excedido o limite, o servidor responde com erro, fecha a conexão e bloqueia o IP por **1 minuto**.

```json
{ "status": "ERROR", "message": "Connection from 203.0.113.42:40046 has been blocked due to excessive login attempts (limit: 50). The block will be lifted in 59 seconds." }
```

- **Registro obrigatório:** `DISCOVER` e `UNREGISTER` só são atendidos para IPs com registro válido (`peer_not_registered` caso contrário).

> **Consequência de projeto:** o intervalo de `DISCOVER` periódico deve ser dimensionado para não estourar o limite. Com `discover_interval = 20 s` e `register_refresh` a cada metade do TTL, um peer consome cerca de 3 req/min — margem ampla. Um bug de laço sem atraso bloqueia o peer em segundos.

### Erros genéricos

| `message` | Causa |
|---|---|
| `Empty request line` | Linha vazia ou apenas espaços |
| `line_too_long` (com campo `limit: 32768`) | Linha acima de 32 KB |
| `Timeout: no data received, closing connection` | Conexão aberta sem envio de dados |
| `Unknown command` | Valor de `type` não reconhecido |

---

## Protocolo Peer–Peer

### Envelope comum

Toda mensagem peer–peer é um objeto JSON com os campos abaixo. Campos específicos de cada tipo são descritos nas seções seguintes.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `type` | string | sim | Tipo da mensagem, em maiúsculas (`HELLO`, `STATE`, ...) |
| `msg_id` | string | sim | UUID v4 gerado pelo emissor. Respostas (`*_OK`, `*_ERR`, `PONG`, `GUESS_RESULT`) **repetem o `msg_id` da mensagem que respondem** |
| `ttl` | inteiro | sim | Sempre `1`. Mensagens com outro valor devem ser descartadas |
| `src` | string | ver nota | `peer_id` do emissor |
| `dst` | string | ver nota | `peer_id` do destinatário |
| `timestamp` | string | ver nota | Instante de emissão em ISO 8601 UTC, ex.: `"2026-10-27T10:00:00Z"` |

**Nota sobre `src`/`dst`/`timestamp`:** `HELLO`, `HELLO_OK`, `PING` e `PONG` são mensagens de **conexão** (o par já está identificado pela conexão TCP) e omitem `src`/`dst`; `PING`/`PONG` carregam `timestamp`. Todas as demais mensagens carregam `src` e `dst` obrigatoriamente. `timestamp` é opcional nas demais e recomendado para logs.

**Regras de processamento:**

- Uma mensagem com `type` desconhecido gera `ERROR` com `code: "unknown_type"` e é descartada; a conexão **permanece aberta**.
- Uma mensagem com `dst` diferente do `peer_id` local é descartada com `ERROR` `code: "not_for_me"` (não há relay).
- Mensagens recebidas em contexto inválido (ex.: `GUESS` fora de partida) geram `ERROR` com `code: "invalid_state"`.
- Campos obrigatórios ausentes ou com tipo errado geram `ERROR` `code: "bad_request"`.

### Mensagens de sessão

#### HELLO / HELLO_OK

Estabelecem a conexão. Enviado por quem **abre** a conexão TCP; quem aceita responde `HELLO_OK`. Até o `HELLO_OK`, nenhuma outra mensagem é aceita.

| Campo | Tipo | Descrição |
|---|---|---|
| `peer_id` | string | Identidade de quem envia |
| `version` | string | Versão do protocolo. Neste trabalho: `"1.0"` |
| `features` | lista de strings | Capacidades suportadas. **Obrigatório conter `"hangman"`**; o peer que não anunciar essa feature é aceito na malha, mas nunca recebe mensagens de lobby/partida |

```json
{ "type": "HELLO", "msg_id": "3b1e...", "peer_id": "alice@CIC", "version": "1.0", "features": ["hangman"], "ttl": 1 }
```

```json
{ "type": "HELLO_OK", "msg_id": "3b1e...", "peer_id": "bob@CIC", "version": "1.0", "features": ["hangman"], "ttl": 1 }
```

**Conexões duplicadas:** como todos os peers tentam conectar-se a todos, é comum que dois peers abram conexões simultâneas um para o outro. Regra de desempate: **mantém-se a conexão aberta pelo peer de menor `peer_id` (ordem lexicográfica)**; a outra é fechada com `BYE` `reason: "duplicate"`. Os alunos devem implementar esse desempate para que o `/conn` mostre exatamente uma conexão por vizinho.

#### PING / PONG

Keep-alive periódico. Enviado por **ambos** os lados de cada conexão a cada `ping_interval` segundos.

| Campo | Tipo | Descrição |
|---|---|---|
| `timestamp` | string | Instante de emissão do PING. O `PONG` **repete o `timestamp` do PING** para permitir cálculo de RTT sem estado adicional |

```json
{ "type": "PING", "msg_id": "9c2a...", "timestamp": "2026-10-27T10:00:00.120Z", "ttl": 1 }
```

```json
{ "type": "PONG", "msg_id": "9c2a...", "timestamp": "2026-10-27T10:00:00.120Z", "ttl": 1 }
```

- RTT = instante de recepção do `PONG` − instante de envio do `PING` correspondente (casado por `msg_id`).
- Após **3 PINGs consecutivos sem PONG**, o peer é marcado `STALE`, a conexão é fechada e a política de reconexão é acionada.
- Se o peer `STALE` era jogador de uma partida hospedada localmente, o host o remove da partida (ver [Tratamento de falhas](#tratamento-de-falhas)).

#### BYE / BYE_OK

Encerramento controlado de uma conexão.

| Campo | Tipo | Descrição |
|---|---|---|
| `reason` | string | Motivo: `"shutdown"`, `"duplicate"`, `"idle"` ou texto livre |

```json
{ "type": "BYE", "msg_id": "d4f0...", "src": "alice@CIC", "dst": "bob@CIC", "reason": "shutdown", "ttl": 1 }
```

```json
{ "type": "BYE_OK", "msg_id": "d4f0...", "src": "bob@CIC", "dst": "alice@CIC", "ttl": 1 }
```

- Quem envia `BYE` aguarda `BYE_OK` por até 2 s e então fecha o socket, com ou sem resposta.
- Quem recebe `BYE` responde `BYE_OK` e fecha o socket.
- Se o peer que envia `BYE` com `reason: "shutdown"` é **host de partida em andamento**, ele deve antes enviar `GAME_OVER` com `result: "ABORTED"` aos jogadores. Se é **jogador**, deve antes enviar `LEAVE`.

#### ERROR

Resposta a mensagens inválidas. Nunca gera contra-resposta.

| Campo | Tipo | Descrição |
|---|---|---|
| `ref_msg_id` | string | `msg_id` da mensagem que causou o erro (se identificável) |
| `code` | string | `unknown_type`, `bad_request`, `not_for_me`, `invalid_state`, `bad_json` |
| `message` | string | Descrição livre para o log |

```json
{ "type": "ERROR", "msg_id": "a1b2...", "src": "bob@CIC", "dst": "alice@CIC", "ref_msg_id": "7e7e...", "code": "invalid_state", "message": "GUESS received but no game running", "ttl": 1 }
```

### Mensagens de lobby

Mensagens que operam antes de a partida começar. Trafegam na malha.

#### GAME_LIST / GAME_LIST_OK

Consulta se um vizinho hospeda partida. O comando `/games` envia `GAME_LIST` a **todos** os vizinhos conectados e consolida as respostas.

**GAME_LIST** — sem campos específicos:

```json
{ "type": "GAME_LIST", "msg_id": "51aa...", "src": "bob@CIC", "dst": "alice@CIC", "ttl": 1 }
```

**GAME_LIST_OK:**

| Campo | Tipo | Descrição |
|---|---|---|
| `games` | lista | Zero ou uma partida (um peer hospeda no máximo uma) |
| `games[].game_id` | string | Identificador da partida |
| `games[].host` | string | `peer_id` do host |
| `games[].status` | string | `"OPEN"` (aceitando jogadores), `"RUNNING"` ou `"FINISHED"` |
| `games[].players` | lista de strings | `peer_id` dos jogadores já inscritos |
| `games[].max_players` | inteiro | Capacidade |
| `games[].lives` | inteiro | Vidas da forca nesta partida |
| `games[].word_length` | inteiro | Tamanho da palavra |

```json
{
  "type": "GAME_LIST_OK", "msg_id": "51aa...", "src": "alice@CIC", "dst": "bob@CIC", "ttl": 1,
  "games": [
    { "game_id": "alice@CIC/3f9a2c1b", "host": "alice@CIC", "status": "OPEN",
      "players": ["carol@CIC"], "max_players": 4, "lives": 6, "word_length": 6 }
  ]
}
```

Um peer sem partida responde `"games": []`.

#### JOIN / JOIN_OK / JOIN_ERR

Entrada de um jogador na partida. Enviado **ao host**.

**JOIN:**

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida desejada (obtida via `GAME_LIST_OK`) |

```json
{ "type": "JOIN", "msg_id": "77c1...", "src": "bob@CIC", "dst": "alice@CIC", "game_id": "alice@CIC/3f9a2c1b", "ttl": 1 }
```

**JOIN_OK:**

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida |
| `players` | lista de strings | Lista atualizada de jogadores, na ordem de entrada |
| `rejoin` | booleano | `true` se o jogador já constava da partida (reconexão); nesse caso o host envia em seguida o `STATE` corrente |

```json
{ "type": "JOIN_OK", "msg_id": "77c1...", "src": "alice@CIC", "dst": "bob@CIC", "game_id": "alice@CIC/3f9a2c1b", "players": ["carol@CIC", "bob@CIC"], "rejoin": false, "ttl": 1 }
```

**JOIN_ERR:**

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida |
| `reason` | string | `unknown_game`, `game_full`, `game_running`, `game_finished`, `already_joined` |

```json
{ "type": "JOIN_ERR", "msg_id": "77c1...", "src": "alice@CIC", "dst": "bob@CIC", "game_id": "alice@CIC/3f9a2c1b", "reason": "game_full", "ttl": 1 }
```

Regras:

- `JOIN` para partida `OPEN` de um `src` desconhecido: aceito se houver vaga.
- `JOIN` para partida `RUNNING` de um `src` que **já era jogador** (reconexão após queda): aceito com `rejoin: true`, seguido de `STATE`.
- `JOIN` para partida `RUNNING` de um `src` novo: `game_running`.
- O host **não** envia `JOIN` para si mesmo — ele não é jogador (ver [Regras do jogo](#regras-do-jogo)).

#### LEAVE / LEAVE_OK

Saída voluntária de um jogador, antes ou durante a partida. Enviado ao host.

```json
{ "type": "LEAVE", "msg_id": "e0e0...", "src": "bob@CIC", "dst": "alice@CIC", "game_id": "alice@CIC/3f9a2c1b", "ttl": 1 }
```

```json
{ "type": "LEAVE_OK", "msg_id": "e0e0...", "src": "alice@CIC", "dst": "bob@CIC", "game_id": "alice@CIC/3f9a2c1b", "ttl": 1 }
```

O host remove o jogador e, se a partida estiver `RUNNING`, difunde um novo `STATE`. Se não restar nenhum jogador, a partida termina com `GAME_OVER` `result: "ABORTED"` (enviado a ninguém, apenas registrado) e volta a `IDLE`.

### Mensagens de partida

Trafegam **apenas host ↔ jogador**.

#### GAME_START

Enviado pelo host a **cada jogador** quando o comando `/start` é executado. Marca a transição `OPEN → RUNNING`.

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida |
| `players` | lista de strings | Ordem definitiva dos turnos (ordem de entrada) |
| `lives` | inteiro | Vidas iniciais |
| `word_length` | inteiro | Tamanho da palavra |
| `word_hash` | string | SHA-256 hexadecimal (minúsculas) da palavra normalizada. Permite ao jogador verificar, no `GAME_OVER`, que o host não alterou a palavra |
| `turn_timeout` | inteiro | Segundos que cada jogador tem por turno |

```json
{
  "type": "GAME_START", "msg_id": "aa10...", "src": "alice@CIC", "dst": "bob@CIC", "ttl": 1,
  "game_id": "alice@CIC/3f9a2c1b",
  "players": ["carol@CIC", "bob@CIC"],
  "lives": 6, "word_length": 6,
  "word_hash": "b493d48364afe44d11c0165cf470a4164d1e2609911ef998be868d46ade3de4e",
  "turn_timeout": 30
}
```

Imediatamente após o `GAME_START`, o host envia o primeiro `STATE` (`seq: 1`).

#### STATE

Estado autoritativo da partida. Enviado pelo host a **todos** os jogadores após **qualquer** mudança: jogada aceita, jogada rejeitada por timeout, entrada/saída de jogador.

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida |
| `seq` | inteiro | Número de sequência, começa em `1` e cresce de 1 a cada `STATE`. O jogador **descarta** `STATE` com `seq` ≤ ao último aplicado |
| `masked` | string | Palavra mascarada, uma posição por caractere: letras reveladas em minúsculas, `_` para as ocultas. Ex.: `"b_n_n_"` |
| `wrong_letters` | lista de strings | Letras erradas já tentadas, em ordem |
| `lives` | inteiro | Vidas restantes (compartilhadas) |
| `turn` | string | `peer_id` de quem deve jogar agora |
| `players` | lista de strings | Jogadores ativos, na ordem de turnos |
| `last_guess` | objeto ou `null` | Última jogada: `{"player": "...", "letter": "a", "correct": true}` ou `{"player": "...", "word": "banana", "correct": false}` |

```json
{
  "type": "STATE", "msg_id": "bb20...", "src": "alice@CIC", "dst": "bob@CIC", "ttl": 1,
  "game_id": "alice@CIC/3f9a2c1b",
  "seq": 3,
  "masked": "_a_a_a",
  "wrong_letters": ["e"],
  "lives": 5,
  "turn": "bob@CIC",
  "players": ["carol@CIC", "bob@CIC"],
  "last_guess": { "player": "carol@CIC", "letter": "e", "correct": false }
}
```

#### GUESS / GUESS_RESULT

Jogada de um jogador, enviada ao host. Exatamente **um** dos campos `letter` ou `word` deve estar presente.

**GUESS:**

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida |
| `letter` | string | Uma letra `a`–`z` |
| `word` | string | Palpite da palavra inteira |

```json
{ "type": "GUESS", "msg_id": "cc30...", "src": "bob@CIC", "dst": "alice@CIC", "game_id": "alice@CIC/3f9a2c1b", "letter": "n", "ttl": 1 }
```

**GUESS_RESULT** — resposta **individual** ao autor da jogada. O efeito da jogada sobre a partida chega a todos pelo `STATE` seguinte.

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida |
| `accepted` | booleano | `true` se a jogada foi processada |
| `reason` | string | Presente se `accepted == false`: `not_your_turn`, `letter_already_used`, `invalid_letter`, `invalid_word`, `game_not_running` |
| `correct` | booleano | Presente se `accepted == true`: `true` se a letra existe na palavra ou a palavra está certa |

```json
{ "type": "GUESS_RESULT", "msg_id": "cc30...", "src": "alice@CIC", "dst": "bob@CIC", "game_id": "alice@CIC/3f9a2c1b", "accepted": true, "correct": true, "ttl": 1 }
```

```json
{ "type": "GUESS_RESULT", "msg_id": "cc31...", "src": "alice@CIC", "dst": "carol@CIC", "game_id": "alice@CIC/3f9a2c1b", "accepted": false, "reason": "not_your_turn", "ttl": 1 }
```

Uma jogada **rejeitada não consome o turno** nem gera `STATE`.

#### GAME_OVER

Enviado pelo host a todos os jogadores ao término. Marca `RUNNING → FINISHED`.

| Campo | Tipo | Descrição |
|---|---|---|
| `game_id` | string | Partida |
| `result` | string | `"WON"` (palavra revelada), `"LOST"` (vidas esgotadas) ou `"ABORTED"` (host encerrou ou nenhum jogador restou) |
| `word` | string | Palavra secreta, revelada |
| `winner` | string ou `null` | `peer_id` de quem completou a palavra (última letra correta ou palpite de palavra certo); `null` se `LOST`/`ABORTED` |
| `scores` | objeto | `peer_id → inteiro`: número de letras corretas reveladas por cada jogador (palpite de palavra correto vale as letras restantes) |
| `reason` | string | Presente se `ABORTED`: `"host_shutdown"`, `"no_players"` |

```json
{
  "type": "GAME_OVER", "msg_id": "dd40...", "src": "alice@CIC", "dst": "bob@CIC", "ttl": 1,
  "game_id": "alice@CIC/3f9a2c1b",
  "result": "WON",
  "word": "banana",
  "winner": "bob@CIC",
  "scores": { "carol@CIC": 2, "bob@CIC": 4 }
}
```

Ao receber `GAME_OVER`, o jogador **deve** calcular `sha256(word)` e comparar com o `word_hash` recebido em `GAME_START`; divergência é registrada no log como `WARNING` (`host cheated: hash mismatch`).

### Regras do jogo

Fixadas pela especificação para garantir que clientes de alunos diferentes joguem entre si sem ambiguidade.

1. **O host não joga.** Ele conhece a palavra e atua como "mestre". São necessários **pelo menos 1 jogador** para iniciar (`/start` com 0 jogadores é recusado localmente).
2. **Palavra:** somente letras `a`–`z`, 3 a 20 caracteres, sem espaços, acentos ou hífens. O host normaliza a palavra recebida no `/create` (minúsculas, remoção de acentos) e recusa se sobrar caractere inválido. O `word_hash` é calculado sobre a palavra normalizada.
3. **Modo cooperativo:** as vidas são compartilhadas — uma única forca. Vidas iniciais: `lives` do `config.json` (padrão 6).
4. **Turnos** em *round-robin* na ordem de `players` do `GAME_START`. Após uma jogada aceita, o turno passa ao próximo, **independentemente de acerto**.
5. **Palpite de letra:** correto se a letra ocorre na palavra (todas as ocorrências são reveladas); incorreto custa 1 vida e a letra vai para `wrong_letters`. Letra já tentada (certa ou errada) é rejeitada com `letter_already_used`.
6. **Palpite de palavra:** correto encerra a partida com `WON`; incorreto custa 1 vida e não revela nada.
7. **Timeout de turno:** se o jogador da vez não jogar em `turn_timeout` segundos, o host passa o turno e difunde `STATE` com `last_guess: {"player": "...", "timeout": true}`. Não custa vida.
8. **Término:** `WON` quando `masked` não contém `_`; `LOST` quando `lives == 0`.
9. **Pontuação:** cada letra revelada por um jogador soma 1 ponto por ocorrência; palpite de palavra correto soma as letras ainda ocultas.
10. **Jogadores que saem** durante a partida são removidos do rodízio; a partida continua enquanto houver ao menos um.

### Máquina de estados

**Host (por partida):**

```
          /create                    /start (≥1 jogador)
  IDLE ───────────► OPEN ─────────────────────────────► RUNNING
    ▲                │ JOIN → JOIN_OK                       │
    │                │ LEAVE → LEAVE_OK                     │ GUESS → GUESS_RESULT + STATE
    │                │ GAME_LIST → GAME_LIST_OK             │ LEAVE → STATE
    │                │                                      │ timeout de turno → STATE
    │                │ /cancel                              │ jogador STALE → STATE
    │                ▼                                      ▼
    └──────────── FINISHED ◄────── GAME_OVER (WON|LOST|ABORTED)
                 (respostas GAME_LIST_OK com status FINISHED por 60 s, depois IDLE)
```

**Jogador:**

```
          /join → JOIN_OK             GAME_START + STATE seq=1
  IDLE ─────────────────► JOINED ────────────────────────────► PLAYING
    ▲                        │                                    │
    │  JOIN_ERR              │ /leave → LEAVE_OK                  │ STATE (seq crescente)
    │                        │                                    │ /guess → GUESS_RESULT
    │                        │                                    │ /leave → LEAVE_OK
    │                        ▼                                    ▼
    └────────────────────────┴───────────────────────── GAME_OVER | host STALE
```

### Tratamento de falhas

| Evento | Detecção | Ação do host | Ação do jogador |
|---|---|---|---|
| Jogador cai | PONG ausente ×3 ou socket fechado | Remove da partida, difunde `STATE`; se era a vez dele, passa o turno; se não resta jogador, `ABORTED` | — |
| Jogador volta | `JOIN` de `src` já conhecido em partida `RUNNING` | `JOIN_OK rejoin:true` + `STATE` corrente; jogador retorna ao fim do rodízio | Reenvia `JOIN` ao reconectar, se estava em partida |
| Host cai | PONG ausente ×3 ou socket fechado | — | Encerra a partida localmente, exibe `[Game] Host alice@CIC unreachable — game aborted`, volta a `IDLE`. Não tenta assumir o papel de host (comportamento mínimo) |
| Host encerra (`/quit`) | `GAME_OVER ABORTED` + `BYE` | Envia `GAME_OVER reason:host_shutdown` a todos antes do `BYE` | Volta a `IDLE` |
| `STATE` fora de ordem | `seq` ≤ último aplicado | — | Descarta e registra `DEBUG` |
| `GUESS` de quem não é a vez | `src != turn` | `GUESS_RESULT not_your_turn` | Exibe aviso |
| Hash divergente | `sha256(word) != word_hash` | — | Log `WARNING` |

**Bônus — migração de host:** ao detectar a queda do host, o jogador de menor `peer_id` (ordem lexicográfica) entre os `players` do último `STATE` assume como novo host, contatando os demais com `GAME_START` de mesmo `game_id` (e novo `word_hash` para uma palavra sorteada por ele). Como a palavra original é desconhecida, a partida recomeça com as vidas do último `STATE`. Trata-se de uma extensão opcional que exercita eleição de líder.

---

## Gerenciamento de Conexões e Reconexões

- Cada peer mantém uma **`PeerTable`** sincronizada com o Rendezvous a cada `discover_interval` segundos.
- Estados de um peer na tabela: `DISCOVERED` (visto no Rendezvous, sem conexão), `CONNECTING`, `CONNECTED` (após `HELLO_OK`), `STALE` (conexão perdida), `GONE` (removido do Rendezvous ou limite de tentativas atingido).
- **Reconciliação:** após cada `DISCOVER`, peers novos entram como `DISCOVERED` e recebem tentativa de conexão; peers ausentes do Rendezvous são marcados `GONE` e a conexão, se houver, é fechada com `BYE`.
- Peers `STALE` recebem tentativas de reconexão com **backoff exponencial** (`base_backoff × 2^n`, limitado a `max_backoff`), até `max_reconnect_attempts`; então viram `GONE` até reaparecerem em um `DISCOVER`.
- Mede-se o RTT por conexão (média móvel dos últimos 10 `PING/PONG`).

---

## Interface de Usuário (CLI)

| Comando | Função |
|---|---|
| `/peers [* \| #namespace]` | Descobrir e listar peers (padrão: namespace local) |
| `/conn` | Listar conexões ativas (inbound/outbound, estado, RTT) |
| `/rtt` | Exibir RTT médio por peer |
| `/reconnect` | Forçar reconciliação imediata com o Rendezvous |
| `/games` | Enviar `GAME_LIST` a todos os vizinhos e listar partidas abertas |
| `/create <palavra> [max_players]` | Criar partida com a palavra informada e tornar-se host |
| `/create --random [max_players]` | Criar partida com palavra sorteada de `words.txt` |
| `/start` | Iniciar a partida hospedada (exige ≥1 jogador) |
| `/cancel` | Cancelar a partida hospedada (`OPEN` ou `RUNNING` → `ABORTED`) |
| `/join <host_peer_id>` | Entrar na partida hospedada pelo peer indicado |
| `/leave` | Sair da partida atual |
| `/guess <letra>` | Enviar palpite de letra |
| `/word <palavra>` | Enviar palpite de palavra inteira |
| `/status` | Exibir estado local da partida (forca, letras, vidas, vez de quem) |
| `/log <nível>` | Ajustar nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `/help` | Listar comandos |
| `/quit` | Encerrar: `LEAVE`/`GAME_OVER` conforme o papel, `BYE` a todos, `UNREGISTER` |

**Exibição mínima do `/status`** (livre, mas deve conter estas informações):

```
[Game] alice@CIC/3f9a2c1b  (host: alice@CIC)  status: RUNNING
[Game] Palavra: _ a _ a _ a     Vidas: 5 / 6     Erradas: e
[Game] Jogadores: carol@CIC, bob@CIC   Vez de: bob@CIC (você)  — 22 s restantes
```

---

## Arquivo de configuração

`config.json` na raiz do projeto, com valores padrão abaixo. Todos podem ser sobrescritos por linha de comando.

```json
{
  "rdv_host": "pyp2p.mfcaetano.cc",
  "rdv_port": 8080,
  "namespace": "CIC",
  "name": "alice",
  "listen_port": 8081,
  "register_ttl": 7200,
  "discover_interval": 20,
  "ping_interval": 30,
  "ping_miss_limit": 3,
  "max_reconnect_attempts": 5,
  "base_backoff": 2,
  "max_backoff": 60,
  "lives": 6,
  "max_players": 4,
  "turn_timeout": 30,
  "words_file": "words.txt",
  "log_file": null
}
```

---

## Arquitetura de Módulos

Sugestão de organização (não obrigatória, mas os critérios de avaliação usam estes nomes nos logs):

| Módulo | Responsabilidade |
|---|---|
| `main.py` | Argumentos, carga do `config.json`, logging, inicialização |
| `p2p_client.py` | Orquestração: registro, tarefas periódicas, encerramento limpo |
| `rendezvous_connection.py` | `REGISTER` / `DISCOVER` / `UNREGISTER` (uma conexão por comando) |
| `peer_connection.py` | Servidor e cliente TCP, framing JSON-por-linha, `HELLO`, desempate de duplicadas |
| `peer_table.py` | Estados dos peers, RTT, backoff, reconciliação |
| `keep_alive.py` | `PING` / `PONG` |
| `message_router.py` | Validação do envelope, despacho por `type` para sessão, lobby ou jogo |
| `game_host.py` | Máquina de estados do host, regras, turnos, timeout, difusão de `STATE` |
| `game_player.py` | Máquina de estados do jogador, verificação de `seq` e de `word_hash` |
| `hangman.py` | Lógica pura do jogo (palavra, máscara, vidas) — **testável sem rede** |
| `cli.py` | Interface de comandos |

Recomenda-se que `hangman.py` não importe nada de rede, para que os alunos possam escrever testes unitários das regras do jogo isoladamente.

---

## Observabilidade e Logs

- Todo evento é registrado com timestamp, nível e módulo de origem.
- Na tela: mensagens `[CLI]`, `[Game]` e `INFO`; no arquivo (`--log-file`): tudo, inclusive `DEBUG` com o JSON bruto de cada mensagem enviada e recebida.
- Exemplos:
  - `[RDV] registered alice@CIC as 45.171.103.246:8081 (ttl=7200)`
  - `[PeerServer] Inbound connected: bob@CIC (features=hangman)`
  - `[PeerServer] Duplicate connection with carol@CIC — keeping outbound (lower peer_id)`
  - `[KeepAlive] bob@CIC RTT=41.7 ms (avg 43.2 ms)`
  - `[KeepAlive] carol@CIC missed 3 PINGs — marking STALE`
  - `[Host] Game alice@CIC/3f9a2c1b created (word_length=6, lives=6)`
  - `[Host] bob@CIC joined (2/4)`
  - `[Host] Turn: bob@CIC (timeout 30 s)`
  - `[Host] GUESS bob@CIC letter=n → correct, masked=_ana_a`
  - `[Host] Turn timeout for carol@CIC — skipping`
  - `[Host] Player carol@CIC STALE — removed from game`
  - `[Player] STATE seq=4 applied: _ana_a lives=5 turn=carol@CIC`
  - `[Player] STATE seq=3 ignored (already at seq=4)`
  - `[Player] GAME_OVER WON word=banana winner=bob@CIC — hash OK`
  - `[Player] Host alice@CIC unreachable — game aborted`

---

## Material Disponibilizado

| Item | Descrição |
|---|---|
| **Servidor Rendezvous público** | `pyp2p.mfcaetano.cc:8080`, sem modificação em relação ao trabalho anterior |
| **Esta especificação** | Protocolo Rendezvous e Peer–Peer, regras do jogo, máquina de estados |
| **Cliente de referência `pyp2p-forca`** | Implementação completa que atua como host e como jogador; serve para testar **interoperabilidade** — o cliente do aluno deve jogar contra ele |
| **Peer-bot `forca-bot`** | Peer que fica registrado no namespace `FORCA` hospedando partidas continuamente com palavras sorteadas e aceitando qualquer `JOIN`; permite que um aluno teste sozinho o ciclo completo |
| **`words.txt`** | Lista de palavras válidas (a–z, 3–20 letras) para o `/create --random` |
| **`config.json` de exemplo** | Com os valores padrão desta especificação |
| **Roteiro de testes** | Passo a passo dos cenários mínimos com a saída esperada |

---

## Critérios de Avaliação

| # | Critério | O que será verificado |
|---|---|---|
| 1 | **Rendezvous** | `REGISTER` com refresh de TTL, `DISCOVER` periódico com filtro do próprio peer, `UNREGISTER` no encerramento; respeito ao limite de taxa |
| 2 | **Conexão TCP** | `HELLO/HELLO_OK` com `features`, desempate de conexões duplicadas, `PING/PONG` com RTT, detecção de `STALE` |
| 3 | **Lobby** | `/games` consolidando `GAME_LIST_OK` de vários vizinhos; `JOIN` com todos os casos de `JOIN_ERR`; `LEAVE` |
| 4 | **Partida como host** | `GAME_START` com `word_hash`, `STATE` com `seq` correto após cada evento, validação completa de `GUESS`, turnos, timeout, `GAME_OVER` com `scores` |
| 5 | **Partida como jogador** | Aplicação de `STATE` com descarte por `seq`, exibição da forca, envio de `GUESS`/`word`, verificação do `word_hash` |
| 6 | **Tolerância a falhas** | Queda de jogador (remoção + `STATE`), reconexão com `rejoin`, queda do host (abort local limpo), `/quit` ordenado |
| 7 | **Interoperabilidade** | Partida completa contra o cliente de referência, nos dois papéis |
| 8 | **CLI e logs** | Todos os comandos funcionais; logs com módulo, timestamp e nível; JSON bruto em `DEBUG` |

**Bônus (opcionais, pontuação extra):** migração de host; modo competitivo (vidas por jogador, vence quem revelar mais letras); chat na partida (`CHAT` difundido pelo host); múltiplas partidas simultâneas por peer; testes unitários de `hangman.py`.

---

## Cenários de Teste Mínimos

1. **Descoberta e malha** — três peers no mesmo namespace registram-se, descobrem-se e o `/conn` de cada um mostra exatamente duas conexões (sem duplicadas).
2. **Partida completa com vitória** — `alice` cria, `bob` e `carol` entram, jogam alternadamente até revelar a palavra; `GAME_OVER WON` com `winner` e `scores` corretos; hash confere.
3. **Partida com derrota** — vidas esgotadas; `GAME_OVER LOST` com `winner: null` e palavra revelada.
4. **Jogada fora do turno** — `carol` envia `GUESS` na vez de `bob`; recebe `not_your_turn`; nenhum `STATE` é gerado.
5. **Letra repetida e palpite de palavra** — `letter_already_used`; `/word` errado custa vida; `/word` certo encerra.
6. **Timeout de turno** — jogador da vez fica inativo por mais de `turn_timeout`; turno passa; `STATE` indica `timeout: true`.
7. **Queda de jogador** — `carol` é encerrada com `kill -9` durante a partida; após 3 PINGs perdidos, `alice` a remove e a partida continua com `bob`.
8. **Reconexão de jogador** — `carol` retorna e envia `JOIN`; recebe `rejoin: true` e o `STATE` corrente; volta ao rodízio.
9. **Queda do host** — `alice` é encerrada com `kill -9`; `bob` e `carol` abortam localmente e voltam a `IDLE`.
10. **Encerramento limpo** — `/quit` no host durante partida gera `GAME_OVER ABORTED` → `BYE/BYE_OK` → `UNREGISTER`, nessa ordem.
11. **Interoperabilidade** — cliente do aluno como jogador contra `forca-bot`; cliente do aluno como host com `pyp2p-forca` como jogador.

---

## Exemplo Completo de Sessão

Trecho de log (nível `DEBUG`, JSON abreviado) de uma partida entre `alice` (host) e `bob` (jogador), palavra `"casa"`.

```
[alice] /create casa 2
[Host]  Game alice@CIC/7d2e9f01 created (word_length=4, lives=6)

[bob]   /games
[bob]   → {"type":"GAME_LIST","msg_id":"m1","src":"bob@CIC","dst":"alice@CIC","ttl":1}
[bob]   ← {"type":"GAME_LIST_OK","msg_id":"m1","src":"alice@CIC","dst":"bob@CIC","ttl":1,
           "games":[{"game_id":"alice@CIC/7d2e9f01","host":"alice@CIC","status":"OPEN",
                     "players":[],"max_players":2,"lives":6,"word_length":4}]}
[CLI]   Partidas abertas:
[CLI]     alice@CIC/7d2e9f01  host=alice@CIC  0/2 jogadores  4 letras  6 vidas

[bob]   /join alice@CIC
[bob]   → {"type":"JOIN","msg_id":"m2","src":"bob@CIC","dst":"alice@CIC","game_id":"alice@CIC/7d2e9f01","ttl":1}
[bob]   ← {"type":"JOIN_OK","msg_id":"m2","src":"alice@CIC","dst":"bob@CIC","game_id":"alice@CIC/7d2e9f01",
           "players":["bob@CIC"],"rejoin":false,"ttl":1}
[Host]  bob@CIC joined (1/2)

[alice] /start
[alice] → {"type":"GAME_START","msg_id":"m3","src":"alice@CIC","dst":"bob@CIC","ttl":1,
           "game_id":"alice@CIC/7d2e9f01","players":["bob@CIC"],"lives":6,"word_length":4,
           "word_hash":"5c7f6a...","turn_timeout":30}
[alice] → {"type":"STATE","msg_id":"m4","src":"alice@CIC","dst":"bob@CIC","ttl":1,
           "game_id":"alice@CIC/7d2e9f01","seq":1,"masked":"____","wrong_letters":[],
           "lives":6,"turn":"bob@CIC","players":["bob@CIC"],"last_guess":null}
[Player] STATE seq=1 applied: ____ lives=6 turn=bob@CIC (você)

[bob]   /guess a
[bob]   → {"type":"GUESS","msg_id":"m5","src":"bob@CIC","dst":"alice@CIC","game_id":"alice@CIC/7d2e9f01","letter":"a","ttl":1}
[bob]   ← {"type":"GUESS_RESULT","msg_id":"m5","src":"alice@CIC","dst":"bob@CIC","game_id":"alice@CIC/7d2e9f01",
           "accepted":true,"correct":true,"ttl":1}
[bob]   ← {"type":"STATE","msg_id":"m6",...,"seq":2,"masked":"_a_a","wrong_letters":[],"lives":6,
           "turn":"bob@CIC","last_guess":{"player":"bob@CIC","letter":"a","correct":true}}

[bob]   /guess e
[bob]   ← {"type":"GUESS_RESULT","msg_id":"m7",...,"accepted":true,"correct":false}
[bob]   ← {"type":"STATE","msg_id":"m8",...,"seq":3,"masked":"_a_a","wrong_letters":["e"],"lives":5,...}

[bob]   /guess a
[bob]   ← {"type":"GUESS_RESULT","msg_id":"m9",...,"accepted":false,"reason":"letter_already_used"}

[bob]   /word casa
[bob]   → {"type":"GUESS","msg_id":"m10","src":"bob@CIC","dst":"alice@CIC","game_id":"alice@CIC/7d2e9f01","word":"casa","ttl":1}
[bob]   ← {"type":"GUESS_RESULT","msg_id":"m10",...,"accepted":true,"correct":true}
[bob]   ← {"type":"GAME_OVER","msg_id":"m11","src":"alice@CIC","dst":"bob@CIC","ttl":1,
           "game_id":"alice@CIC/7d2e9f01","result":"WON","word":"casa","winner":"bob@CIC",
           "scores":{"bob@CIC":4}}
[Player] GAME_OVER WON word=casa winner=bob@CIC — hash OK
[Host]  Game alice@CIC/7d2e9f01 finished: WON by bob@CIC
```
