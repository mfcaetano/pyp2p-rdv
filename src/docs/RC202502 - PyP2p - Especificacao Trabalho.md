# Trabalho de Programação — **Chat P2P (Versão Revisada)**

## Sumário

- [Trabalho de Programação — **Chat P2P (Versão Revisada)**](#trabalho-de-programação--chat-p2p-versão-revisada)
  - [Sumário](#sumário)
  - [Resumo](#resumo)
  - [Arquitetura P2P: Conceitos, Características e Atuadores](#arquitetura-p2p-conceitos-características-e-atuadores)
    - [Características Principais](#características-principais)
    - [Atores em Uma Redes P2P](#atores-em-uma-redes-p2p)
    - [Considerações Finais](#considerações-finais)
  - [Objetivos](#objetivos)
  - [Identidade e Escopo](#identidade-e-escopo)
  - [Transporte e Codificação](#transporte-e-codificação)
  - [Parametrização (config.json)](#parametrização-configjson)
  - [Integração com o Servidor Rendezvous](#integração-com-o-servidor-rendezvous)
  - [Protocolo de Comunicação entre Peers](#protocolo-de-comunicação-entre-peers)
    - [HELLO / HELLO\_OK](#hello--hello_ok)
    - [PING / PONG](#ping--pong)
    - [SEND / ACK](#send--ack)
    - [PUB](#pub)
    - [BYE / BYE\_OK](#bye--bye_ok)
  - [Gerenciamento de Conexões e Reconexões](#gerenciamento-de-conexões-e-reconexões)
  - [Interface de Usuário (CLI)](#interface-de-usuário-cli)
  - [Arquitetura de Módulos](#arquitetura-de-módulos)
  - [Observabilidade e Logs](#observabilidade-e-logs)
  - [Critérios de Avaliação](#critérios-de-avaliação)
  - [Cenários de Teste Mínimos](#cenários-de-teste-mínimos)

---

## Resumo

Este trabalho consiste na implementação de um **cliente de Chat P2P** que:

- Registra-se em um **servidor Rendezvous**;
- Descobre outros peers ativos de forma recorrente e automática;
- Mantém **conexões TCP persistentes** com eles;
- Troca mensagens em tempo real por meio de **comandos de chat** (`SEND`, `PUB`);
- Mantém sessões vivas com **PING/PONG** e as encerra de forma limpa com **BYE/BYE_OK**.

O projeto implementa um sistema P2P de conexão direta — **não há relay ou múltiplos saltos**. Cada peer comunica-se diretamente apenas com os peers alcançáveis.

---

## Arquitetura P2P: Conceitos, Características e Atuadores

A **arquitetura peer-to-peer (P2P)** constitui um modelo de comunicação distribuída no qual cada nó da rede, denominado *peer*, exerce simultaneamente as funções de cliente e servidor. Diferentemente do paradigma cliente-servidor, em que existe uma entidade central responsável por fornecer serviços, no modelo P2P a interação ocorre de forma descentralizada, com múltiplos pontos de origem e destino. Esse modelo tornou-se amplamente utilizado em aplicações de compartilhamento de arquivos, redes de sobreposição (*overlay networks*), sistemas de mensageria e ambientes colaborativos.

### Características Principais

1. **Descentralização**  
    A inexistência de uma autoridade central reduz o risco de ponto único de falha e distribui a responsabilidade entre os peers. Essa característica aumenta a autonomia da rede e dificulta a censura ou controle centralizado.

2. **Escalabilidade**  
    O aumento no número de participantes contribui positivamente para a capacidade global da rede. Cada peer adicional introduz novos recursos de conectividade e processamento, tornando o sistema naturalmente escalável.

3. **Resiliência**  
    A arquitetura P2P é intrinsecamente tolerante a falhas. A saída de um peer não compromete o funcionamento da rede, uma vez que outros peers podem assumir o encaminhamento ou a redistribuição dos recursos.

4. **Distribuição de Recursos**  
    Dados e serviços são fragmentados e replicados entre diferentes peers. Esse mecanismo evita sobrecarga em um único ponto e promove redundância, o que contribui para maior disponibilidade e desempenho.

5. **Heterogeneidade**  
    Os peers podem apresentar capacidades heterogêneas em termos de largura de banda, poder de processamento e tempo de disponibilidade. Apesar disso, todos podem colaborar de acordo com suas possibilidades, reforçando a flexibilidade do modelo.

6. **Dinamicidade**  
    A rede P2P é marcada por intensa variação na participação dos peers (*churn*). Protocolos e aplicações P2P devem, portanto, lidar com a entrada e saída frequente de nós, preservando a consistência e a utilidade da rede.

### Atores em Uma Redes P2P

No contexto da arquitetura P2P, os atuadores correspondem aos papéis ou funções desempenhadas pelos peers para sustentar o funcionamento da rede:

1. **Peers de Origem e Destino**  
    Responsáveis pela emissão e recepção final de mensagens ou dados. Em um sistema de chat, por exemplo, representam os usuários que trocam mensagens diretamente.

2. **Peers de Encaminhamento (*Relay Peers*)**  
    Fundamentais quando não existe rota direta entre origem e destino, especialmente em cenários com NAT ou firewalls. Esses peers atuam como nós de encaminhamento na camada de aplicação, propagando mensagens até o destino. **Neste trabalho, o papel de relay não é implementado**, focando-se apenas em conexões diretas.

3. **Peers de Descoberta**  
    Participam dos mecanismos de identificação e localização de outros nós. No trabalho proposto, **servidor Rendezvous** é o "ponto de encontro" inicial dos peers, responsável por registrar e listar peers ativos. Como os peers entram em saem da rede de forma dinâmica e inexperada, a descoberta contínua é essencial para manter a conectividade.

4. **Peers de Observabilidade**  
    Monitoram o estado da rede, incluindo métricas como tempo de resposta (RTT), disponibilidade de rotas e falhas de encaminhamento. Essas informações auxiliam na tomada de decisão sobre o roteamento de mensagens.

### Considerações Finais

A arquitetura P2P representa um paradigma **colaborativo, escalável e resiliente**, no qual cada peer pode assumir diferentes papéis de acordo com sua posição e conectividade na rede. Para que esse modelo funcione de maneira eficiente, é necessário o suporte a mecanismos de **descoberta de peers, encaminhamento de mensagens, tolerância a falhas e atualização dinâmica da topologia**.  

No contexto deste trabalho de programação, a implementação de um cliente P2P permitirá ao estudante vivenciar esses conceitos na prática, ao interagir com o servidor Rendezvous, estabelecer conexões diretas com outros peers e trocar mensagens respeitando as restrições de tempo de vida (*time-to-live*, TTL) definidas no protocolo.

---

## Objetivos

1. Exercitar conceitos de **arquitetura P2P** e **protocolos de aplicação**;
2. Implementar um cliente P2P capaz de:
    - Registrar-se no Rendezvous (`REGISTER` / `UNREGISTER`);
    - Descobrir peers de forma recorrente e automática (`DISCOVER`);
    - Estabelecer conexões TCP com peers acessíveis;
    - Enviar mensagens diretas e de broadcast;
    - Manter conexões ativas com *keep-alive* (`PING/PONG`);
    - Fechar conexões corretamente (`BYE/BYE_OK`).

---

## Identidade e Escopo

Cada peer é identificado como `name@namespace`, por exemplo `alice@CIC`.

- **namespace**: agrupador lógico (ex.: `UnB`, `CIC`).
- **name**: identificador único dentro do namespace.
- **peer_id**: formado por `name@namespace`.

**Escopos de envio:**

- **Unicast** → `peer_id` (ex.: `/msg bob@CIC hello`)
- **Namespace-cast** → `#namespace` (ex.: `/pub #CIC hello all`)
- **Broadcast global** → `*` (ex.: `/pub * system maintenance`)

---

## Transporte e Codificação

- **Transporte:** TCP
- **Codificação:** JSON UTF-8, delimitado por `\n`
- **Tamanho máximo:** 32 KiB (32768 bytes)
- **TTL:** fixo em `1` (não decrementa)
- **Keep-alive:** PING a cada 30 segundos (intervalo configurável)
- **Timeout:** conexões fechadas em caso de erro de leitura/escrita

---

## Parametrização (config.json)

O cliente deve ler suas configurações iniciais a partir de um arquivo `config.json` localizado na raiz do projeto. Este arquivo centraliza os parâmetros de rede, temporizadores (timeouts/intervalos) e limites da aplicação.

O formato estrutural obrigatório do arquivo é o seguinte:

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
````
---

## Protocolo de Comunicação entre Peers

### HELLO / HELLO_OK

Estabelecem a conexão inicial.

**HELLO:**

```json
{
   "type": "HELLO",
   "peer_id": "alice@UnB",
   "version": "1.0",
   "features": ["ack", "metrics"],
   "ttl": 1
}
```

**HELLO_OK:**

```json
{
   "type": "HELLO_OK",
   "peer_id": "bob@UnB",
   "version": "1.0",
   "features": ["ack", "metrics"],
   "ttl": 1
}
```

Após o handshake, a conexão é mantida aberta para troca de mensagens.

### PING / PONG

Mensagens periódicas de keep-alive.

**PING:**

```json
{
   "type": "PING",
   "msg_id": "uuid",
   "timestamp": "2025-10-27T10:00:00Z",
   "ttl": 1
}
```

**PONG:**

```json
{
   "type": "PONG",
   "msg_id": "uuid",
   "timestamp": "2025-10-27T10:00:00Z",
   "ttl": 1
}
```

O RTT é calculado e registrado nos logs.

### SEND / ACK

Mensagens diretas entre dois peers.

**SEND:**

```json
{
   "type": "SEND",
   "msg_id": "uuid",
   "src": "alice@UnB",
   "dst": "bob@UnB",
   "payload": "Olá!",
   "require_ack": true,
   "ttl": 1
}
```

**ACK:**

```json
{
   "type": "ACK",
   "msg_id": "uuid",
   "timestamp": "2025-10-27T10:00:01Z",
   "ttl": 1
}
```

Mensagens sem ACK após 5s geram aviso de timeout no log.

### PUB

Permite difusão para todos os peers conectados.

**Namespace-cast:**

```json
{
   "type": "PUB",
   "msg_id": "uuid",
   "src": "alice@UnB",
   "dst": "#UnB",
   "payload": "Aviso para todos!",
   "require_ack": false,
   "ttl": 1
}
```

**Broadcast:**

```json
{
   "type": "PUB",
   "msg_id": "uuid",
   "src": "alice@UnB",
   "dst": "*",
   "payload": "Mensagem global",
   "require_ack": false,
   "ttl": 1
}
```

### BYE / BYE_OK

Finalizam a sessão de forma controlada.

**BYE:**

```json
{
   "type": "BYE",
   "msg_id": "uuid",
   "src": "alice@UnB",
   "dst": "bob@UnB",
   "reason": "Encerrando sessão",
   "ttl": 1
}
```

**BYE_OK:**

```json
{
   "type": "BYE_OK",
   "msg_id": "uuid",
   "src": "bob@UnB",
   "dst": "alice@UnB",
   "ttl": 1
}
```

---

## Gerenciamento de Conexões e Reconexões

- Cada peer mantém uma **tabela de peers** (`PeerTable`) sincronizada com o Rendezvous.
- Peers que não respondem são marcados como `STALE`.
- Tentativas de reconexão seguem política de **backoff exponencial**.
- O número máximo de tentativas é definido em `config.json` (`max_reconnect_attempts`).

---

## Interface de Usuário (CLI)

Comandos disponíveis:

| Comando | Função |
|----------|--------|
| `/peers [* \| #namespace]` | Descobrir e listar peers |
| `/msg <peer_id> <mensagem>` | Enviar mensagem direta |
| `/pub * <mensagem>` | Enviar broadcast global |
| `/pub #<namespace> <mensagem>` | Enviar mensagem para todos do namespace |
| `/conn` | Mostrar conexões ativas (inbound/outbound) |
| `/rtt` | Exibir RTT médio por peer |
| `/reconnect` | Forçar reconciliação de peers |
| `/log <Nível>` | Ajustar nível de log (DEBUG, INFO...) |
| `/quit` | Encerrar aplicação |

---

## Arquitetura de Módulos

Sugestão de organização do código em módulos:

- **`main.py`** — inicializa aplicação e logging
- **`p2p_client.py`** — lógica principal (registro, descoberta, reconexão, CLI)
- **`rendezvous_connection.py`** — comunicação com servidor Rendezvous
- **`peer_connection.py`** — controle das conexões TCP e mensagens entre peers
- **`message_router.py`** — envio e publicação de mensagens
- **`keep_alive.py`** — gerenciamento de PING/PONG
- **`peer_table.py`** — controle de estado e reconexões
- **`state.py`** — armazenamento dos peers conhecidos
- **`cli.py`** — interface de linha de comando

---

## Observabilidade e Logs

- Todos os eventos são registrados com timestamp e módulo de origem.
- Logs de INFO e CLI podem ser exibidos na tela; logs detalhados vão para arquivo (se configurado).
- Exemplo de mensagens de log:
  - `[PeerServer] Inbound connected: alice@CIC`
  - `[Router] SEND bob@CIC: oi!`
  - `[KeepAlive] Sent 2 PINGs | Average RTT = 43.2 ms`

---

## Critérios de Avaliação

1. **Rendezvous** — registro, descoberta e unregistro funcionais.
2. **Conexão TCP** — estabelecimento HELLO/HELLO_OK e manutenção com PING/PONG.
3. **Mensageria** — `SEND` com ACK e `PUB` global/namespace.
4. **Encerramento** — BYE/BYE_OK funcionando.
5. **Reconexão** — tentativa automática com limite configurável.
6. **CLI e Logs** — comandos e observabilidade implementados.

---

## Cenários de Teste Mínimos

1. **Conexão direta** — dois peers no mesmo namespace trocando mensagens via `SEND` e `PUB`.
2. **Descoberta automática** — peers se registram e se descobrem periodicamente.
3. **Keep-alive** — verificação de PING/PONG e RTT nos logs.
4. **Reconexão** — peer desconectado e reconectado automaticamente.
5. **Encerramento** — envio e recepção de BYE/BYE_OK.
6. **CLI** — execução dos comandos principais (`/msg`, `/pub`, `/rtt`, `/conn`, `/quit`).
