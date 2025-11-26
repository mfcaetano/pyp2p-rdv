## Rendezvous - Protocolo de Aplicação do Servidor Rendezvous

Esta documentação **apresenta somente** o protocolo de camada de aplicação de interação com o servidor redezvous.

#### Visão Geral

O **servidor rendezvous** atua como um ponto central de encontro para peers em uma rede P2P.  

- Cada **peer** deve **registrar-se** no servidor para ficar visível.  
- Peers podem **descobrir** outros participantes em uma determinada sala (**namespace**).  
- Peers podem também **remover** seu registro (**unregister**).  
- Todos os registros têm um **tempo de vida (TTL)** em segundos. Expirado esse tempo, o registro é descartado automaticamente.  

A comunicação é feita sobre **TCP**. Cada **conexão aceita apenas um comando (uma linha JSON)** e é encerrada após a resposta.

---

#### Formato das mensagens

- Cada mensagem (requisição ou resposta) é um objeto **JSON válido**, enviado em **uma única linha** terminada por `\n`.  
- O servidor impõe um limite de **32 KB por linha**.  
- Se a linha for vazia ou apenas espaços, o servidor responde com um erro.  

---

#### Comandos aceitos

##### 1. `REGISTER`

Registra (ou atualiza) um peer no servidor.

**Campos obrigatórios:**

- `type`: `"REGISTER"`
- `namespace`: string (até 64 caracteres)  
- `name`: string (até 64 caracteres)  
- `port`: inteiro (1–65535)  

**Campos opcionais:**

- `ttl`: inteiro em segundos (1–86400). Se omitido, assume **7200 (2h)**.

**Exemplo de requisição:**

```json

{ "type": "REGISTER", "namespace": "UnB", "name": "alice", "port": 4000, "ttl": 3600 }
```

**Resposta de sucesso:**

```json
{"status": "OK", "ttl": 3600, "ip": "45.171.103.246", "port": 4000}
```

**Possíveis erros:**

Seguem alguns exemplo possíveis de erros retornados pelo servidor para requisições `REGISTER` inválidas:

- Quando o valor do campo `name` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_name" }
```

- Quando o valor do campo `namespace` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_namespace" }
```

- Quando o valor do campo `ttl` não é um inteiro.

```json
{ "status": "ERROR", "message": "bad_ttl" }
```

> **Obs:** O valor do campo `ttl` deve estar entre 1 e 86400 (24 horas). Valores fora desse intervalo, o servidor assume `max(1, min(ttl, 86400))` e não retorna erro.

- Quando o valor do campo `port` é inválido (> 65535 ou < 1):

```json
{ "status": "ERROR", "message": "bad_port" }
```

---

##### 2. `DISCOVER`
Retorna a lista de peers registrados em um *namespace*. O servidor **apenas responde** às requisições dos *peers* com registros válidos (não expirados). Para maiores informações, consulte a seção [4. Proteção contra abusos](#4-proteção-contra-abusos).

**Campos:**

- `type`: `"DISCOVER"`
- `namespace`: string (opcional).  
  - Se omitido, retorna todos os peers de todos os namespaces.
  - `namespace` inexistente, o servidor retorna uma lista vazia.

**Exemplo de requisição:**

```json

{ "type": "DISCOVER", "namespace": "UnB" }
```

**Resposta:**

```json
{
  "status": "OK",
  "peers": [
    {
      "ip": "45.171.103.246",
      "port": 4000,
      "name": "alice",
      "namespace": "UnB",
      "ttl": 3600,
      "expires_in": 3527
    }
  ]
}
```

**Requisição omitindo `namespace`**

```json
{ "type": "DISCOVER" }
```

**Resposta:**

```json
{
  "status": "OK",
  "peers": [
    {
      "ip": "45.171.101.167",
      "port": 8081,
      "name": "vm_giga",
      "namespace": "CIC",
      "ttl": 7200,
      "expires_in": 5908
    },
    {
      "ip": "45.171.103.246",
      "port": 4000,
      "name": "alice",
      "namespace": "UnB",
      "ttl": 3600,
      "expires_in": 3592
    }
  ]
}
```

**Requisição para `namespace` inexistente**
```json
{ "type": "DISCOVER", "namespace": "know-without-study" }
```

**Resposta:**
```json
{"status": "OK", "peers": []}
```

**Erros possíveis:**

Seguem alguns exemplo possíveis de erros retornados pelo servidor para requisições `DISCOVER` inválidas:

- Quando o valor do campo `namespace` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_namespace" }
```

- Quando o *peer* que fez a requisição (`IP`) não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

> **Obs:** Não é possível desregistrar um *peer* que não está registrado.

---

##### 3. `UNREGISTER`

Remove *peers* previamente registrados. O servidor **apenas responde** às requisições dos *peers* com registros válidos (não expirados). Para maiores informações, consulte a seção [4. Proteção contra abusos](#4-proteção-contra-abusos).

**Campos obrigatórios:**
- `type`: `"UNREGISTER"`
- `namespace`: string 

**Campos opcionais:**
- `name`: string  
- `port`: inteiro  

**Exemplo de requisição:**
```json
{ "type": "UNREGISTER", "namespace": "room1", "name": "peerA", "port": 4000 }
```

**Resposta de sucesso:**
```json
{ "status": "OK" }
```

**Erros possíveis:**

Seguem alguns exemplo possíveis de erros retornados pelo servidor para requisições `UNREGISTER` inválidas:

- Quando o valor do campo `port` não é um inteiro válido ou está fora do intervalo 1-65535:

```json
{ "status": "ERROR", "message": "bad_port (abc)" }
```

- Quando o valor do campo `namespace` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_namespace" }
```

- Quando o *peer* que fez a requisição não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

- Quando o campo **obrigatório** `namespace` está ausente na requisição:

```json
{ "status": "ERROR", "message": "namespace_required" }
```

- Quando o *peer* que fez a requisição não corresponde ao registro (`IP`) ou algum campo informado é divergente ao registrado (`namespace`, `port` ou `name`):

```json
{ "status": "ERROR", "message": "peer_credentials_do_not_match" }
```
> **Dica:** realize o debug do código utilizando o comando **`DISCOVER`** para verificar os dados registrados do *peer*. 

- Quando o *peer* que fez a requisição (`IP`) não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

> **Obs:** Não é possível desregistrar um *peer* que não está registrado.

---

##### 4. Proteção contra abusos

Para evitar abusos, o servidor impõe as seguintes restrições:

- Cada *peer* pode encaminhar 50 requisições por minuto. Excedido esse limite, o servidor passa a não atender as requisições e a responder com erro e fecha a conexão. O usuário fica banido por 1 minuto. Passado esse período, o servidor passa a liberar o acesso novamente.

**Resposta exemplo para um IP bloqueado:**

```json
{
  "status": "ERROR",
  "message": "Connection from 203.0.113.42:40046 has been blocked due to excessive login attempts (limit: 50). The block will be lifted in 59 seconds."
}
```

- É obrigatório fazer o registro antes de usar DISCOVER ou UNREGISTER. Caso contrário, o servidor responde com erro e fecha a conexão. Quando o *peer* que fez a requisição (`IP`) não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

---

##### 5. Mensagens de Erro Genéricas

- Linha vazia ou só espaços:
```json
{ "status": "ERROR", "message": "Empty request line" }
```

- Linha muito longa (> 32768 bytes):
```json
{ "status": "ERROR", "message": "line_too_long", "limit": 32768 }
```

- Timeout de inatividade:
```json
{ "status": "ERROR", "message": "Timeout: no data received, closing connection" }
```

- Comando desconhecido:
```json
{ "status": "ERROR", "message": "Unknown command" }
```

---

#### Resumo do Ciclo de Uso

1. O cliente se conecta ao servidor rendezvous (IP: pyp2p.mfcaetano.cc e TCP/8080 por padrão).  
2. Envia um **REGISTER** para se anunciar.  
3. Usa **DISCOVER** para consultar peers de um namespace.  
4. Pode **UNREGISTER** ao sair.  
5. Se o TTL expirar, o registro desaparece automaticamente.  
