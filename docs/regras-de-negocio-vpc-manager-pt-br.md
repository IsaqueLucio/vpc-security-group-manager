# Regras de Negócio — vpc-security-group-manager (Fase 01)

Projeto de portfólio: API em FastAPI para gestão de VPCs, sub-redes e alocação de IP, usado como preparação para a vaga de Desenvolvedor(a) Júnior — VPC (Magalu Cloud). Documento consolidado com todas as decisões de Fase 01, organizadas em 5 grupos.

---

## Grupo 1 — VPC

**Atributos:** `id` (UUID), `name` (obrigatório), `cidr_block` (CIDR IPv4), `description` (opcional), `region` (obrigatório), `status` (`PENDING | ACTIVE | ERROR | DELETED`), `created_at` / `updated_at` (UTC).

| RN | Nome | Regra |
|---|---|---|
| 1.1 | Posse (ownership) | VPCs pertencem a um usuário individual. Nome é único por dono, não globalmente — dois usuários diferentes podem ter VPCs com o mesmo nome. |
| 1.2 | Unicidade exata de CIDR | Duplicata exata de CIDR é rejeitada dentro do mesmo dono. (Na prática, redundante com a RN 1.6, que cobre overlap — decidir na implementação se mantém como checagem separada por clareza de mensagem de erro, ou se é só um caso particular do overlap.) |
| 1.3 | Faixa de prefixo | Prefixo da VPC entre `/16` e `/28` (padrão AWS-like). |
| 1.4 | CIDR privado/público | Ambos permitidos (RFC 1918 e faixas públicas). Um aviso (warning) não bloqueante é retornado quando o CIDR é público. |
| 1.5 | CIDRs reservados | Rejeitar criação se o CIDR estiver contido em `0.0.0.0/8`, `127.0.0.0/8`, `169.254.0.0/16`, `224.0.0.0/4` ou `240.0.0.0/4`. "Contido em", não só "igual a". |
| 1.6 | Overlap entre VPCs do mesmo dono | Nenhuma VPC de um usuário pode ter CIDR que se sobreponha (total ou parcialmente) ao de outra VPC do mesmo usuário. Entre usuários diferentes, overlap é permitido. A checagem ignora VPCs com `status = DELETED`. |
| 1.7 | Canonicalização estrita | CIDR com bits de host fora da máscara (ex.: `10.0.5.0/16`) é rejeitado com erro claro — nunca mascarado/corrigido silenciosamente. |
| 1.8 | Limite de VPCs por usuário | Limite fixo, configurável por variável de ambiente (padrão sugerido: 5, mesma cota padrão da AWS por região/conta). |
| 1.9 | Exclusão de VPC | Exclusão em cascata: exclui/inativa (soft delete) os recursos filhos (sub-redes, IP allocations). `status` passa a `DELETED`. A cascata é síncrona, na mesma transação (RN 3.3). |
| 1.10 | Máquina de estados | `PENDING` na criação → um job em background transiciona para `ACTIVE` após um intervalo configurável, simulando provisionamento assíncrono. `ERROR` reservado para falhas de um provider adapter real (fase futura). `DELETED` via soft delete (RN 1.9). |

---

## Grupo 2 — CIDR, Sub-redes e Endereços IP

**Atributos da sub-rede:** `id` (UUID), `vpc_id` (obrigatório), `name` (obrigatório), `cidr_block`, `type` (`PUBLIC | PRIVATE`, obrigatório), `availability_zone` (opcional, sem validação ainda), `status` (mesma máquina de estados da VPC), `created_at` / `updated_at`.

**Atributos do IP Allocation:** `id` (UUID), `subnet_id` (obrigatório), `ip_address`, `description`/`label` (opcional), `status`, `created_at` / `updated_at`.

| RN | Nome | Regra |
|---|---|---|
| 2.1 | Criação de sub-rede | Duas formas: CIDR manual, ou alocação automática a partir de um tamanho/prefixo desejado. **Automática é o padrão** quando o cliente não envia `cidr_block`. |
| 2.2 | Contenção | O CIDR da sub-rede deve estar inteiramente contido no CIDR da VPC-mãe. |
| 2.3 | Overlap entre sub-redes irmãs | Duas sub-redes da mesma VPC não podem se sobrepor. Entre VPCs diferentes, não há comparação. |
| 2.4 | Faixa de prefixo da sub-rede | `/16`–`/28`, e o prefixo deve ser **igual ou maior** (rede igual ou menor) que o da VPC-mãe. |
| 2.5 | Algoritmo de alocação automática | First-fit: percorre os blocos candidatos do tamanho pedido em ordem crescente a partir do início do CIDR da VPC, retorna o primeiro sem overlap, ignorando sub-redes com soft delete. |
| 2.6 | Tipo da sub-rede | `type` é metadado declarado pelo usuário na criação (`PUBLIC` ou `PRIVATE`), sem valor padrão — obrigatório informar. Sem semântica de roteamento real (Internet Gateway/NAT) na Fase 01; isso fica para uma futura fase de Route Tables. |
| 2.7 | Zona de disponibilidade | Campo `availability_zone` existe desde já, mas sem validação na Fase 01. Regra futura (adiada, sem catálogo de regiões/zonas ainda): a AZ da sub-rede deve pertencer à `region` da VPC-mãe. |
| 2.8 | Status da sub-rede | Sub-rede reutiliza a mesma máquina de estados da VPC (`PENDING | ACTIVE | ERROR | DELETED`). |
| 2.9 | Reserva de IPs por sub-rede | Convenção AWS: os 4 primeiros endereços (rede, gateway reservado, 2 reservados pelo provedor) e o último endereço (broadcast) de cada sub-rede ficam bloqueados para alocação. Numa `/24` (256 endereços), sobram 251 utilizáveis. |
| 2.10 | Modelo de alocação de IP | Recurso genérico `IP Allocation`, não vinculado a uma instância computacional real — reserva um endereço dentro de uma sub-rede. Manual (endereço específico) ou automático (padrão), reusando a mesma lógica first-fit da RN 2.5 no nível de endereço único. |
| 2.11 | Unicidade de IP | Dois `IP Allocation` ativos na mesma sub-rede não podem apontar para o mesmo endereço. A checagem ignora alocações com soft delete. |
| 2.12 | Liberação de IP | Ao excluir (soft delete) um `IP Allocation`, o endereço volta a ficar disponível para alocações futuras. |

---

## Grupo 3 — CRUD e Comportamento da API

| RN | Nome | Regra |
|---|---|---|
| 3.1 | Imutabilidade | Campos estruturais (`cidr_block`, `vpc_id`, `subnet_id`) são imutáveis após a criação. Só `name`, `description` e (em sub-rede) `type` podem ser alterados via `PATCH`. |
| 3.2 | Guarda de estado operacional *(corrigida)* | Criação de recurso filho só é bloqueada se o pai estiver `DELETED` ou `ERROR`. **Não bloqueia se o pai estiver `PENDING`** — evita a corrida com a transição assíncrona da RN 1.10/2.8. |
| 3.3 | Cascata de exclusão | Síncrona, dentro da mesma transação: excluir uma VPC marca todos os descendentes ativos (sub-redes, IP allocations) como `DELETED` na mesma operação. |
| 3.4 | Listagem | Endpoints de listagem suportam paginação e filtros relevantes (ex.: por `status`, `type`, `vpc_id`). |
| 3.5 | Mapeamento de códigos de erro | `422` para payload estruturalmente/matematicamente inválido (CIDR malformado, prefixo fora da faixa). `409` para payload válido que conflita com o estado atual (duplicata, overlap, cota excedida, esgotamento do first-fit, pai em estado que bloqueia criação de filho). `404` para recurso inexistente **ou** pertencente a outro usuário (RN 4.2) **ou** tentativa de mutação sobre recurso `DELETED`. |
| 3.6 | Avisos não bloqueantes | Mensagens de aviso (ex.: CIDR público, RN 1.4) retornadas na resposta sem impedir a operação. |
| 3.7 | Métricas calculadas | Resposta de sub-rede inclui `total_ips`, `usable_ips` (`total_ips - 5`), `available_ips` (`usable_ips` menos alocações ativas). Nunca negativo, pois o menor prefixo permitido (`/28`) garante `usable_ips >= 11`. |
| 3.8 | Semântica de exclusão | `DELETE` retorna `200` com o recurso em estado `DELETED`. Uma segunda tentativa de exclusão sobre um recurso já `DELETED` retorna `404` (não é idempotente no sentido de sempre devolver sucesso). |
| 3.9 | Desenho de rotas | Rotas aninhadas para criação/listagem sob o recurso pai (ex.: `POST/GET /vpcs/{id}/subnets`). Rotas diretas para operações sobre um único recurso (`GET/PATCH/DELETE /subnets/{id}`). |

---

## Grupo 4 — Segurança e RBAC

| RN | Nome | Regra |
|---|---|---|
| 4.1 | Posse herdada pela hierarquia | `owner_id` é armazenado apenas na VPC, não duplicado em sub-rede/IP allocation — a posse dos filhos é sempre resolvida subindo até a VPC. |
| 4.2 | 404 em vez de 403 entre usuários | Tentativa de acessar/alterar recurso de outro usuário retorna `404` (não `403`), para não confirmar a existência do recurso a quem não tem acesso (anti-enumeração). |
| 4.3 | Privilégios de admin | Usuário `admin` tem acesso de leitura/escrita a recursos de qualquer dono. |
| 4.4 | Autenticação obrigatória | Todos os endpoints exigem JWT válido. |
| 4.5 | Delegação de `owner_id` | Só `admin` pode definir `owner_id` na criação, em nome de outro usuário. Usuário comum não tem esse campo disponível — implementado via **schemas Pydantic separados** (um para usuário comum, sem o campo; outro para admin, com o campo opcional), não como checagem de permissão em runtime. |
| 4.6 | Validações no contexto do dono correto | Cota (RN 1.8), unicidade e overlap, quando um admin cria em nome de outro usuário, são validados contra o `owner_id` de destino, nunca contra o `owner_id` do próprio admin. |
| 4.7 | Verificação de usuário ativo | Toda requisição autenticada confirma que a conta do usuário está ativa, reaproveitando a mesma consulta já feita para resolver o usuário a partir do JWT (sem consulta extra). |
| 4.8 | `status` somente leitura via API pública | `status` não é alterável via `PATCH` por usuários comuns — só muda pelo ciclo de vida interno (job em background da RN 1.10, cascata da RN 1.9, ou, opcionalmente, um endpoint restrito a admin para forçar transições). |

---

## Grupo 5 — Persistência

| RN | Nome | Regra |
|---|---|---|
| 5.1 | Motor de banco de dados | PostgreSQL como padrão da aplicação, com Docker Compose para desenvolvimento local e CI. |
| 5.2 | Concorrência na alocação first-fit | Lock pessimista (`SELECT ... FOR UPDATE`) no recurso pai antes de calcular o first-fit, **mais** constraint de exclusão no banco (GiST) como rede de segurança. Timeout de lock não obtido → `503` com `Retry-After`. Constraint do banco disparando apesar do lock → `409`. |
| 5.3 | Tipos nativos de rede | `cidr_block` e `ip_address` usam os tipos nativos `CIDR`/`INET` do PostgreSQL, não `VARCHAR`. |
| 5.4 | UUID e timestamps gerados pelo banco | `id` via `gen_random_uuid()` (extensão `pgcrypto`). `created_at`/`updated_at` via `server_default`/`server_onupdate`, nunca calculados na aplicação. |
| 5.5 | Constraint de exclusão para overlap (nível de banco) | `EXCLUDE USING gist` (extensão `btree_gist`) em `vpcs` (`owner_id` igual + `cidr_block` sobrepondo) e em `subnets` (`vpc_id` igual + `cidr_block` sobrepondo), filtradas por `status != 'DELETED'`. Garantia final para a RN 1.6/2.3, independente de bug futuro na aplicação. |
| 5.6 | Índices únicos parciais | `UNIQUE (owner_id, name) WHERE status != 'DELETED'` em `vpcs`; `UNIQUE (vpc_id, name) WHERE status != 'DELETED'` em `subnets`; `UNIQUE (subnet_id, ip_address) WHERE status != 'DELETED'` em `ip_allocations`. |
| 5.7 | Índices de performance | Índices B-tree em `vpcs(owner_id)`, `vpcs(status)`, `subnets(vpc_id)`, `subnets(status)`, `ip_allocations(subnet_id)`, `ip_allocations(status)`. |
| 5.8 | Integridade referencial | Foreign keys com `ON DELETE RESTRICT` (nunca `CASCADE`) — o sistema nunca faz exclusão física, só soft delete (RN 1.9/3.3); `RESTRICT` protege contra um `DELETE` físico acidental. |
| 5.9 | Checks de banco (defesa em profundidade) | `masklen(cidr_block) BETWEEN 16 AND 28` em `vpcs`/`subnets`; `status` como `ENUM` nativo do PostgreSQL, não `VARCHAR` livre. |
| 5.10 | Migrations via Alembic | Schema gerido só por migrations revisadas manualmente (autogenerate não captura `EXCLUDE`/`CHECK` de forma confiável). `Base.metadata.create_all()` não roda fora de testes unitários isolados sem Postgres. |
| 5.11 | Isolamento de transação | `READ COMMITTED` (padrão do PostgreSQL) é suficiente, já que a concorrência é resolvida por lock explícito (RN 5.2), não por isolamento mais estrito. |
| 5.12 | Testes contra PostgreSQL real | Testes de integração rodam contra PostgreSQL real (Testcontainers), nunca SQLite — tipos nativos, `EXCLUDE USING gist` e índices parciais não têm equivalente fiel no SQLite. |

---

## Fora de escopo (adiado explicitamente)

- Arquivamento/expurgo de registros com `status = DELETED` antigos.
- Particionamento de tabelas.
- Réplicas de leitura.
- Route Tables / Internet Gateway / NAT reais (semântica de roteamento por trás do `type` da sub-rede).
- Catálogo de regiões/zonas de disponibilidade (validação da RN 2.7).
