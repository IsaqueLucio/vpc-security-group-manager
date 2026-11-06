# Documentação da API

Este documento descreve a API HTTP atualmente implementada pelo VPC & Security
Group Manager. Exemplos usam `http://localhost:8000`; ajuste a URL se a API
estiver em outro host.

## Visão geral

- Documentação interativa: <http://localhost:8000/docs>
- Especificação OpenAPI: <http://localhost:8000/openapi.json>
- Todas as rotas de negócio exigem um JWT válido, exceto `POST /auth/login`.
- `POST /auth/register` exige um usuário já autenticado.
- Envie o token em `Authorization: Bearer <token>`.
- Identificadores de VPC, Subnet e IPAllocation são UUIDs.
- Recursos de rede são removidos logicamente: sua resposta passa a ter status
  `DELETED`, em vez de a linha ser apagada.

Os exemplos de shell usam `jq` para extrair valores JSON.

`/docs`, `/redoc` e `/openapi.json` são páginas/documentos do FastAPI; não são
rotas de negócio. A especificação e a interface Swagger ficam acessíveis sem
token.

## Fluxo esperado

1. Obtenha uma conta admin por provisionamento operacional. Não há endpoint
   público para criar o primeiro admin.
2. Faça login em `POST /auth/login` para obter um token.
3. Use uma conta autenticada para registrar usuários comuns com
   `POST /auth/register`.
4. Faça login como cada usuário. Cada pessoa deve usar seu próprio bearer
   token para criar e consultar recursos.
5. Crie uma VPC. Ela inicia como `PENDING` e é ativada após o intervalo
   configurado.
6. Crie Subnets dentro da VPC; o sistema escolhe um CIDR livre por padrão ou
   aceita um CIDR manual válido.
7. Crie IPAllocations dentro de uma Subnet; por padrão, o primeiro IP
   utilizável livre é escolhido.
8. Use PATCH para atualizar somente os campos editáveis; use DELETE para
   marcar recursos como `DELETED`.

### Criar usuários e obter tokens

O login recebe formulário `application/x-www-form-urlencoded`. O campo
`username` deve conter o e-mail cadastrado.

```bash
ADMIN_TOKEN=$(curl -sS -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin@example.com' \
  --data-urlencode 'password=<senha-admin>' | jq -r .access_token)
```

Uma conta autenticada pode registrar um novo usuário. O endpoint só cria
usuários comuns; `role` não pode ser escolhido no corpo.

```bash
curl -sS -X POST http://localhost:8000/auth/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "alice",
    "email": "alice@example.com",
    "password": "StrongPassword@123"
  }'
```

A senha deve ter ao menos 8 caracteres, uma letra maiúscula, um número e um
caractere especial de `!@#$%^&*()_+-=`.

Faça login com cada conta que for usar:

```bash
ALICE_TOKEN=$(curl -sS -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice@example.com' \
  --data-urlencode 'password=StrongPassword@123' | jq -r .access_token)
```

O token é um bearer token assinado e contém o ID e a role emitidos no login. A
API carrega o usuário pelo ID e usa a role atualmente armazenada no banco para
autorizar operações. Usuários inativos ou inexistentes são rejeitados com
`401`, inclusive quando apresentam um JWT que ainda não expirou.

## Autenticação, ownership e roles

### Usuário comum

- Só lista e opera VPCs que possui.
- A posse de Subnets e IPAllocations é determinada seguindo a relação
  Subnet → VPC → owner; `owner_id` existe somente na VPC.
- Se tentar ler, alterar, excluir ou criar um recurso sob um pai que não
  possui, recebe `404 Not Found`.
- Não pode informar `owner_id` ao criar VPC.

### Admin

- Pode listar e operar VPCs, Subnets e IPAllocations de qualquer proprietário.
- Pode criar uma VPC para outro usuário enviando `owner_id`.
- Se omitir `owner_id`, a VPC criada pertence ao próprio admin.
- Cota, unicidade de nome e verificação de overlap na criação são calculadas
  para o proprietário de destino.

O endpoint `GET /users/me` devolve o perfil da conta autenticada. As rotas
`/admin/users` exigem role `admin`; essa autorização administrativa retorna
`403` quando a conta autenticada não é admin.

## Formato de respostas e erros

As respostas de erro da aplicação seguem este formato:

```json
{
  "detail": "Descrição do erro."
}
```

Erros de validação de entrada gerados pelo FastAPI podem retornar um array de
detalhes em `detail`.

| HTTP | Uso comum |
| --- | --- |
| `200 OK` | Consulta, alteração ou exclusão lógica concluída |
| `201 Created` | Usuário, VPC, Subnet ou IPAllocation criado |
| `204 No Content` | Usuário excluído pela rota administrativa |
| `401 Unauthorized` | JWT ausente, inválido ou expirado; conta inexistente/inativa; credenciais inválidas |
| `403 Forbidden` | Usuário autenticado sem role admin tentando usar uma rota exclusiva de admin |
| `404 Not Found` | Recurso inexistente, excluído ou pertencente a outro usuário |
| `409 Conflict` | Nome/CIDR/IP duplicado, overlap, cota excedida, esgotamento ou estado que impede a operação |
| `422 Unprocessable Entity` | Corpo ou parâmetro inválido; CIDR não canônico/reservado; campo não editável |
| `503 Service Unavailable` | Timeout ao aguardar lock de alocação; a resposta inclui `Retry-After` |

Uma segunda exclusão de um recurso que já está `DELETED` retorna `404`.

## Endpoints de autenticação e usuários

### `POST /auth/login`

Público. Autentica por e-mail e senha.

**Content-Type:** `application/x-www-form-urlencoded`

| Campo | Obrigatório | Descrição |
| --- | --- | --- |
| `username` | Sim | E-mail da conta |
| `password` | Sim | Senha |

**Resposta `200`:**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Credenciais incorretas ou usuário inativo retornam `401`.

### `POST /auth/register`

Exige JWT de uma conta ativa. Cria somente usuário comum.

**Corpo:**

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "StrongPassword@123"
}
```

- `username`: 3 a 50 caracteres.
- `email`: e-mail válido e único.
- `password`: no mínimo 8 caracteres, com maiúscula, número e caractere
  especial permitido.
- `role` e `is_active` não são campos de criação aceitos como configuração; a
  rota sempre cria uma conta ativa com role `user`.

**Resposta `201`:**

```json
{
  "id": 12,
  "username": "alice",
  "email": "alice@example.com",
  "role": "user"
}
```

Senha ou hash não são incluídos na resposta. E-mail ou nome de usuário
duplicado retorna `409`.

### `GET /users/me`

Exige JWT. Devolve `id`, `username`, `email` e `role` da conta autenticada.

### `GET /`

Exige JWT. Retorna o nome e o estado de inicialização da API.

### `GET /health`

Exige JWT. Retorna `{"status":"ok"}` quando o processo da API está respondendo.

### `GET /admin/users`

Exige role `admin`. Devolve a lista de usuários no formato `UserRead`.

### `DELETE /admin/users/{user_id}`

Exige role `admin`. Exclui o usuário e retorna `204 No Content`. Um admin não
pode excluir a própria conta (`409`); usuário inexistente retorna `404`.

## Endpoints de VPC

Status possíveis: `PENDING`, `ACTIVE`, `ERROR` e `DELETED`. Ao criar, a VPC
começa em `PENDING`; uma tarefa em background a altera para `ACTIVE` depois do
intervalo configurado. A tarefa é em memória e não persiste se o processo da
API parar.

CIDRs devem ser IPv4 canônicos, com prefixo entre `/16` e `/28`. O CIDR não
pode conter bits de host fora da máscara nem estar em uma faixa reservada.
CIDRs públicos são aceitos, mas a resposta contém um aviso.

### `POST /vpcs`

Cria VPC para o usuário autenticado. Nome, CIDR duplicado ou overlap com uma
VPC ativa do mesmo proprietário resultam em `409`; a cota por proprietário
também pode resultar em `409`.

**Corpo para usuário comum:**

```json
{
  "name": "production",
  "cidr_block": "10.20.0.0/16",
  "description": "Rede de produção",
  "region": "us-east-1"
}
```

`name` deve ter 3 a 100 caracteres. `description` é opcional. `region` deve
ser uma das regiões listadas em `GET /docs`/OpenAPI.

Usuário comum não tem o campo `owner_id` no schema; se enviar esse campo, a
requisição é rejeitada com `422`.

**Criação admin para outro usuário:**

```json
{
  "name": "production",
  "cidr_block": "10.20.0.0/16",
  "description": "Rede de produção",
  "region": "us-east-1",
  "owner_id": 12
}
```

`owner_id` é opcional para admin e deve ser um inteiro positivo. Omiti-lo
atribui a VPC ao admin. O proprietário de destino deve existir. Nome,
quota, CIDR duplicado e overlap são verificados para o proprietário indicado.

**Resposta `201` (exemplo):**

```json
{
  "id": "de305d54-75b4-431b-adb2-eb6b9e546014",
  "name": "production",
  "cidr_block": "10.20.0.0/16",
  "description": "Rede de produção",
  "region": "us-east-1",
  "status": "PENDING",
  "created_at": "2026-11-05T12:00:00Z",
  "updated_at": "2026-11-05T12:00:00Z",
  "warnings": []
}
```

`warnings` conterá uma mensagem se o CIDR for público.

### `GET /vpcs`

Lista VPCs ativas. Usuário comum vê as próprias; admin vê as de todos os
proprietários.

Query parameters:

| Parâmetro | Padrão | Restrições |
| --- | --- | --- |
| `skip` | `0` | Maior ou igual a zero |
| `limit` | `20` | Entre 1 e 100 |

### `GET /vpcs/{vpc_id}`

Retorna uma VPC ativa visível para a conta. Usuário sem ownership recebe `404`.

### `PATCH /vpcs/{vpc_id}`

Altera somente `name` e/ou `description`. Envie ao menos um campo. `name` deve
ter 3 a 100 caracteres e não pode ser `null`; `description` pode ser `null`.
`status`, `cidr_block`, `region` e `owner_id` não são editáveis via PATCH.

```json
{
  "name": "production-renamed",
  "description": "Descrição atualizada"
}
```

Campo não permitido, incluindo `status`, retorna `422`.

### `DELETE /vpcs/{vpc_id}`

Marca a VPC como `DELETED`. Na mesma transação, marca também como `DELETED`
Subnets e IPAllocations ativos descendentes. Retorna a VPC excluída.

## Endpoints de Subnet

Status possíveis: `PENDING`, `ACTIVE`, `ERROR` e `DELETED`. Uma Subnet pode ser
criada enquanto a VPC está `PENDING`; VPC `ERROR` ou `DELETED` não aceita
novas Subnets.

Tipo obrigatório:

- `PUBLIC`
- `PRIVATE`

O CIDR deve ser IPv4 canônico, ter prefixo de `/16` a `/28`, estar contido na
VPC e não sobrepor outra Subnet ativa da mesma VPC.

### `POST /vpcs/{vpc_id}/subnets`

Cria Subnet sob uma VPC acessível.

**Alocação automática (padrão `/24`):**

```json
{
  "name": "private-a",
  "type": "PRIVATE"
}
```

Para escolher outro tamanho, use `prefix_length` (16 a 28):

```json
{
  "name": "private-b",
  "type": "PRIVATE",
  "prefix_length": 26,
  "availability_zone": "us-east-1a"
}
```

**Alocação manual:**

```json
{
  "name": "public-a",
  "type": "PUBLIC",
  "cidr_block": "10.20.1.0/24",
  "availability_zone": "us-east-1a"
}
```

Envie `cidr_block` ou `prefix_length`, não ambos. `availability_zone` é
opcional; quando informada, precisa pertencer ao catálogo estático da região
da VPC. O catálogo atual inclui `sa-east-1`, `us-east-1`, `us-west-2` e
`eu-west-1`. Região não catalogada ou zona de outra região retorna `422`.
PATCH também valida alterações de `availability_zone`; enviar `null` limpa
esse campo.

A alocação automática bloqueia a linha da VPC durante a seleção do primeiro
bloco livre. O timeout de lock é configurado por `DATABASE_LOCK_TIMEOUT_MS`
(padrão `5000` ms). Timeout retorna `503` com `Retry-After`; conflito de
overlap retorna `409`.

**Resposta `201` (exemplo):**

```json
{
  "id": "39a00000-0000-4000-8000-000000000001",
  "vpc_id": "de305d54-75b4-431b-adb2-eb6b9e546014",
  "name": "private-a",
  "cidr_block": "10.20.0.0/24",
  "type": "PRIVATE",
  "availability_zone": null,
  "status": "PENDING",
  "created_at": "2026-11-05T12:00:00Z",
  "updated_at": "2026-11-05T12:00:00Z",
  "total_ips": 256,
  "usable_ips": 251,
  "available_ips": 251
}
```

`total_ips` é o total matemático de endereços. `usable_ips` exclui os quatro
primeiros e o último endereço da Subnet; `available_ips` subtrai os IPs
alocados ativos de `usable_ips`.

### `GET /vpcs/{vpc_id}/subnets`

Lista Subnets ativas da VPC, após validar que a VPC pertence ao usuário ou que
o usuário é admin. Aceita `skip` (padrão `0`, mínimo `0`) e `limit` (padrão
`20`, entre `1` e `100`).

### `GET /subnets/{subnet_id}`

Retorna uma Subnet ativa acessível, com métricas de capacidade e disponibilidade.

### `PATCH /subnets/{subnet_id}`

Altera somente `name` e/ou `type`. Envie pelo menos um campo. `name` tem entre
1 e 100 caracteres; `type` é `PUBLIC` ou `PRIVATE`. Também é possível alterar
`availability_zone` usando uma zona existente no catálogo da região da VPC.
Enviar `null` remove a zona. Status, CIDR e VPC não são alteráveis por PATCH.

### `DELETE /subnets/{subnet_id}`

Marca a Subnet e suas IPAllocations e NAT Gateways ativos como `DELETED` na
mesma transação. Retorna a Subnet excluída.

## Endpoints de IPAllocation

IPAllocation representa a reserva de um endereço IPv4 utilizável dentro de
uma Subnet. O endereço da rede, os três endereços seguintes e o broadcast
(quatro primeiros mais o último) são reservados.

### `POST /subnets/{subnet_id}/ip-allocations`

Cria uma alocação. O corpo vazio seleciona automaticamente o primeiro IP livre.

```json
{}
```

Para solicitar um IP específico:

```json
{
  "ip_address": "10.20.0.20",
  "description": "Servidor da aplicação"
}
```

O IP manual deve ser IPv4 utilizável, estar dentro da Subnet e não estar
alocado. IP reservado ou fora da Subnet retorna `422`; duplicidade retorna
`409`. Sem endereços disponíveis, retorna `409`.

A criação bloqueia a linha da Subnet enquanto confere disponibilidade e grava
a alocação. Timeout retorna `503` com header `Retry-After`. A unicidade ativa
também é protegida pelo índice único do banco.

**Resposta `201` (exemplo):**

```json
{
  "id": "39a00000-0000-4000-8000-000000000002",
  "subnet_id": "39a00000-0000-4000-8000-000000000001",
  "ip_address": "10.20.0.20",
  "description": "Servidor da aplicação",
  "status": "ACTIVE",
  "created_at": "2026-11-05T12:00:00Z",
  "updated_at": "2026-11-05T12:00:00Z"
}
```

### `GET /subnets/{subnet_id}/ip-allocations`

Lista IPAllocations ativas de uma Subnet acessível. Uma Subnet inexistente,
excluída ou de outro owner retorna `404`.

### `GET /ip-allocations/{allocation_id}`

Retorna uma IPAllocation ativa acessível. Uma alocação excluída ou pertencente
a outro owner retorna `404`.

### `DELETE /ip-allocations/{allocation_id}`

Marca a alocação como `DELETED` e retorna a representação atualizada. O
endereço fica disponível para reutilização dentro da mesma Subnet.

## Endpoints de Gateways

Os gateways nesta fase são apenas cadastros e validações. Não há simulação de
roteamento ou tráfego de pacotes. Ambos são criados com status `ACTIVE` e
removidos logicamente com status `DELETED`.

### `POST /vpcs/{vpc_id}/internet-gateways`

Cria um Internet Gateway na VPC acessível. Não recebe corpo. É permitido no
máximo um gateway com status diferente de `DELETED` por VPC. Um segundo ativo
retorna `409`; a regra é garantida também por índice único parcial do
PostgreSQL.

### `GET /vpcs/{vpc_id}/internet-gateways`

Lista Internet Gateways ativos da VPC acessível.

### `DELETE /internet-gateways/{gateway_id}`

Marca o Internet Gateway como `DELETED`. A resposta contém o gateway alterado;
depois disso, outro gateway pode ser criado para a VPC.

### `POST /subnets/{subnet_id}/nat-gateways`

Cria NAT Gateway na Subnet acessível. Não recebe corpo. A Subnet deve ter
`type: "PUBLIC"`; para `PRIVATE`, a resposta é `422`.

### `GET /subnets/{subnet_id}/nat-gateways`

Lista NAT Gateways ativos da Subnet acessível.

### `DELETE /nat-gateways/{gateway_id}`

Marca o NAT Gateway como `DELETED` e devolve o recurso atualizado.

Todas essas rotas exigem JWT e respeitam ownership. Recursos de outro dono
retornam `404` para usuários comuns; admins podem acessá-los. A exclusão da
Subnet ou da VPC também marca gateways descendentes como `DELETED` na mesma
transação.

Exemplo:

```bash
curl -X POST "http://localhost:8000/vpcs/<vpc-id>/internet-gateways" \
  -H "Authorization: Bearer $TOKEN"
curl -X POST "http://localhost:8000/subnets/<public-subnet-id>/nat-gateways" \
  -H "Authorization: Bearer $TOKEN"
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/subnets/<public-subnet-id>/nat-gateways"
```

## Endpoints de Route Tables

Route Tables são cadastradas por VPC. Rotas configuram destinos, mas não
simulam encaminhamento de pacotes. Os targets aceitos são `LOCAL`,
`INTERNET_GATEWAY` e `NAT_GATEWAY`. IGW e NAT Gateway devem estar ativos e
pertencer à mesma VPC da Route Table. `LOCAL` exige `target_id: null` ou campo
omitido; os outros targets exigem um UUID válido. CIDR inválido/não canônico,
target ausente/inativo/de outra VPC retorna `422`.

### `POST /vpcs/{vpc_id}/route-tables`

Cria uma Route Table na VPC acessível:

```json
{"name": "main"}
```

### `GET /vpcs/{vpc_id}/route-tables`

Lista as Route Tables ativas da VPC.

### `GET /route-tables/{route_table_id}`

Retorna uma Route Table acessível.

### `DELETE /route-tables/{route_table_id}`

Marca a Route Table, suas rotas ativas e associações ativas como `DELETED` na
mesma transação.

### `POST /route-tables/{route_table_id}/routes`

Cria uma rota. Exemplos:

```json
{
  "destination_cidr": "0.0.0.0/0",
  "target_type": "INTERNET_GATEWAY",
  "target_id": "<internet-gateway-id>"
}
```

```json
{"destination_cidr": "10.20.0.0/16", "target_type": "LOCAL"}
```

### `GET /route-tables/{route_table_id}/routes`

Lista as rotas ativas da Route Table.

### `DELETE /routes/{route_id}`

Marca a rota como `DELETED`.

### `POST /subnets/{subnet_id}/route-table-association`

Associa uma Subnet a uma Route Table:

```json
{"route_table_id": "<route-table-id>"}
```

Subnet e Route Table precisam pertencer à mesma VPC. Uma Subnet pode ter no
máximo uma associação ativa; tentar criar outra retorna `409` sem substituir
a associação existente. Após excluir a associação, outra pode ser criada.

### `DELETE /subnets/{subnet_id}/route-table-association`

Marca a associação ativa da Subnet como `DELETED`.

Todas as rotas exigem JWT e ownership é conferido pela VPC ancestral. Usuários
sem acesso recebem `404`; admins podem operar recursos de outros donos.
Excluir uma Subnet ou VPC também marca suas associações e rotas descendentes
como `DELETED` na mesma transação.

Exemplo de fluxo manual:

```bash
TABLE_ID=$(curl -sS -X POST "http://localhost:8000/vpcs/<vpc-id>/route-tables" \
  -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' \
  -d '{"name":"main"}' | jq -r .id)
curl -X POST "http://localhost:8000/route-tables/$TABLE_ID/routes" \
  -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' \
  -d '{"destination_cidr":"10.20.0.0/16","target_type":"LOCAL"}'
curl -X POST "http://localhost:8000/subnets/<subnet-id>/route-table-association" \
  -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' \
  -d "{\"route_table_id\":\"$TABLE_ID\"}"
```

## Endpoints de VPC Peering

VPC Peering registra uma solicitação entre duas VPCs; não implementa
encaminhamento de pacotes. As VPCs devem ser distintas e seus CIDRs não podem
se sobrepor (`409`). Uma solicitação começa em `PENDING_ACCEPTANCE`.

### `POST /vpc-peerings`

Cria peering. Usuário comum só pode usar uma VPC própria como `requester`;
admin pode criar para qualquer proprietário.

```json
{
  "requester_vpc_id": "<requester-vpc-id>",
  "accepter_vpc_id": "<accepter-vpc-id>"
}
```

CIDR sobreposto ou par já pendente/ativo retorna `409`. O par é normalizado no
índice único do PostgreSQL, portanto enviar as mesmas VPCs na ordem inversa
também retorna `409`. Pares rejeitados ou cancelados podem ser solicitados
novamente. VPC inexistente/inativa ou requester de outro proprietário retorna
`404`; tentar usar a mesma VPC nos dois lados retorna `422`.

### `GET /vpc-peerings`

Lista peerings não excluídos dos quais o usuário autenticado participa como
requester ou accepter. Admin recebe a lista de todos.

### `PATCH /vpc-peerings/{peering_id}`

Aceita ou rejeita uma solicitação pendente:

```json
{"status": "ACTIVE"}
```

```json
{"status": "REJECTED"}
```

Somente o proprietário da VPC accepter ou admin pode alterar o estado. Se o
requester tentar aceitar/rejeitar, recebe `403`; um usuário que não participa
recebe `404`. Transições para estados diferentes de `ACTIVE` e `REJECTED`, ou
uma alteração depois da decisão, são rejeitadas (`422`/`409`).

### `DELETE /vpc-peerings/{peering_id}`

O proprietário da VPC requester ou admin pode cancelar enquanto o estado for
`PENDING_ACCEPTANCE`. A operação é soft delete (`DELETED`); accepter sem role
admin recebe `403` e usuário alheio recebe `404`. Excluir uma VPC também marca
seus peerings não excluídos como `DELETED`.

Exemplo de fluxo entre dois usuários:

```bash
# Alice cria uma solicitação da VPC dela para a VPC de Bob.
curl -X POST http://localhost:8000/vpc-peerings \
  -H "Authorization: Bearer <alice-token>" \
  -H 'Content-Type: application/json' \
  -d '{"requester_vpc_id":"<alice-vpc-id>","accepter_vpc_id":"<bob-vpc-id>"}'

# Bob lista solicitações recebidas e aceita uma como accepter.
curl -H "Authorization: Bearer <bob-token>" \
  http://localhost:8000/vpc-peerings
curl -X PATCH "http://localhost:8000/vpc-peerings/<peering-id>" \
  -H "Authorization: Bearer <bob-token>" \
  -H 'Content-Type: application/json' \
  -d '{"status":"ACTIVE"}'
```

## Exemplo completo com dois usuários

O exemplo pressupõe que `ADMIN_TOKEN` tenha sido obtido como mostrado acima,
e que `jq` esteja instalado. O admin registra Alice e Bob; Alice cria a VPC,
Subnet e alocação; Bob não consegue ler a VPC de Alice; o admin consegue.

```bash
# Criar contas comuns (a rota de registro requer uma conta autenticada).
curl -sS -X POST http://localhost:8000/auth/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"StrongPassword@123"}'
curl -sS -X POST http://localhost:8000/auth/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob","email":"bob@example.com","password":"StrongPassword@123"}'

# Login de cada usuário.
ALICE_TOKEN=$(curl -sS -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice@example.com' \
  --data-urlencode 'password=StrongPassword@123' | jq -r .access_token)
BOB_TOKEN=$(curl -sS -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=bob@example.com' \
  --data-urlencode 'password=StrongPassword@123' | jq -r .access_token)

# Alice cria uma VPC.
VPC_ID=$(curl -sS -X POST http://localhost:8000/vpcs \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"alice-vpc","cidr_block":"10.20.0.0/16","region":"us-east-1"}' \
  | jq -r .id)

# Alice cria uma Subnet e obtém automaticamente o primeiro bloco /24.
SUBNET_ID=$(curl -sS -X POST "http://localhost:8000/vpcs/$VPC_ID/subnets" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"private-a","type":"PRIVATE"}' | jq -r .id)

# Alice reserva automaticamente o primeiro endereço utilizável.
curl -sS -X POST "http://localhost:8000/subnets/$SUBNET_ID/ip-allocations" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{}'

# Bob não é proprietário: recebe 404 (não 403).
curl -i -H "Authorization: Bearer $BOB_TOKEN" \
  "http://localhost:8000/vpcs/$VPC_ID"

# O admin consegue consultar recursos de qualquer owner.
curl -i -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/vpcs/$VPC_ID"
```

## Variáveis de configuração relacionadas

Consulte `.env.example` para a lista completa. As principais variáveis que
afetam os fluxos documentados:

| Variável | Efeito |
| --- | --- |
| `SECRET_KEY` | Chave de assinatura JWT; use segredo aleatório de pelo menos 32 caracteres |
| `ALGORITHM` | Algoritmo JWT; padrão `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Validade do token; padrão `30` minutos |
| `VPC_LIMIT_PER_OWNER` | Cota de VPCs ativas por proprietário; padrão `5` |
| `VPC_PROVISIONING_DELAY_SECONDS` | Atraso antes de a VPC passar de `PENDING` para `ACTIVE`; padrão `30` segundos |
| `DATABASE_LOCK_TIMEOUT_MS` | Espera máxima por lock de alocação; padrão `5000` ms |

## Observações operacionais

- A API usa PostgreSQL e o schema deve ser aplicado com `alembic upgrade head`.
- Não envie `SECRET_KEY`, senhas ou tokens em repositórios ou logs públicos.
- A ativação de VPC é uma tarefa em memória do processo; não é uma fila durável.
- A lista completa de rotas e schemas fica disponível em `/docs` e
  `/openapi.json`.
