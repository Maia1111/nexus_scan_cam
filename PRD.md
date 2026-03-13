# PRD — IP Camera Scanner (versão Flet)
**Data:** 2026-03-13  
**Status do projeto:** Em desenvolvimento ativo  
**Base de referência:** scanner_camera (v2.0, CustomTkinter) — versão funcional

---

## 1. VISÃO GERAL

Aplicação desktop para descoberta, monitoramento e gerenciamento de câmeras IP em redes locais. Público-alvo: técnicos de CFTV, administradores de rede e equipes de segurança.

---

## 2. FUNCIONALIDADES CORE — STATUS ATUAL

### Legenda
- ✅ Implementado e funcionando
- ⚠️ Implementado mas com problemas
- ❌ Não implementado (existe no v2.0)
- 🔧 Parcialmente implementado

---

## 3. MÓDULO: AUTENTICAÇÃO

| Funcionalidade | Status | Observação |
|---|---|---|
| Tela de login com usuário e senha | ✅ | OK |
| Validação de credenciais (bcrypt) | ✅ | OK |
| Papéis: ADMIN / VIEWER | ✅ | OK (falta OPERATOR do v2.0) |
| Papel: OPERATOR | ❌ | Existe no v2.0, falta aqui |
| Logout com limpeza de estado | ✅ | OK |
| Primeiro setup (sem usuários) | ❌ | v2.0 tinha FirstSetupWindow |
| Gerenciamento de usuários (CRUD) | ❌ | Existe AdminView no v2.0 |
| Ativar/desativar usuários | ❌ | Existe no v2.0 |
| Campo "Nome completo" no usuário | ❌ | Existe no v2.0 |

---

## 4. MÓDULO: DASHBOARD

| Funcionalidade | Status | Observação |
|---|---|---|
| Card: Total de câmeras | ✅ | OK |
| Card: Câmeras online | ✅ | OK |
| Card: Alertas/offline | ✅ | OK |
| Card: Câmeras desconhecidas | ❌ | Existe no v2.0 (4 cards, não 3) |
| Barra de proporção online/offline | ❌ | Gráfico de barra no v2.0 |
| Painel de ações rápidas | ❌ | Botões de atalho no v2.0 |
| Lista de câmeras recentes | ❌ | "Câmeras Recentes" no v2.0 |
| Botão "Atualizar" manual | ❌ | v2.0 tinha botão de refresh |
| Atualização automática via monitor | ✅ | OK |

---

## 5. MÓDULO: SCANNER DE REDE

| Funcionalidade | Status | Observação |
|---|---|---|
| Campo CIDR com auto-detecção | ✅ | Corrigido — usa get_local_network() |
| Botão Iniciar Scan | ⚠️ | Funciona, mas não exibe estado "Escaneando..." no botão |
| Botão Parar Scan | ✅ | OK |
| Barra de progresso | ✅ | OK |
| Contador de hosts encontrados | ❌ | v2.0 exibia "🌐 256 host(s)" |
| Contador de câmeras encontradas | ❌ | v2.0 exibia "📷 5 câmera(s)" |
| Card de resultado com marca | ✅ | OK |
| Card com portas abertas | ✅ | OK |
| Card com score de confiança | ✅ | OK |
| Badge visual de portas (RTSP, HTTP...) | ❌ | v2.0 tinha badges coloridos por protocolo |
| Barra de score no card | ❌ | v2.0 tinha barra verde/laranja |
| Detecção ONVIF multicast | ✅ | OK |
| Detecção ONVIF unicast | ✅ | OK |
| Botão "Salvar" no card de resultado | ✅ | OK |
| Indicador "Já adicionada" no botão | ❌ | v2.0 mostrava "✓ Adicionada" se já no banco |
| Empty state: "Pronto para escanear" | ❌ | v2.0 tinha 3 estados visuais |
| Empty state: "Nenhum host encontrado" | ❌ | v2.0 tinha mensagem específica |
| Empty state: "Nenhuma câmera detectada" | ❌ | v2.0 tinha mensagem específica |
| Validação CIDR (rejeitar rede > 1024) | ❌ | v2.0 validava e exibia erro |
| Toast/notificação de conclusão | ❌ | v2.0 tinha "Scan concluído — N câmeras" |
| Detecção de marca por HTTP banner | ❌ | v2.0 fazia GET e lia Server + title |
| Resolução de nome da câmera | ❌ | v2.0 tentava ONVIF + HTTP + DNS reverso |
| Scan em 2 fases (discover → analyse) | ❌ | v2.0 era mais eficiente |

---

## 6. MÓDULO: LISTA DE CÂMERAS

| Funcionalidade | Status | Observação |
|---|---|---|
| Tabela com Status, Marca, IP | ✅ | OK |
| Coluna de latência | ✅ | OK |
| Coluna de grupo | ✅ | OK |
| Coluna de localização | ✅ | OK |
| Busca por IP/marca/MAC | ✅ | OK |
| Filtro "Somente offline" | ✅ | OK |
| Filtro: Todas / Online / Offline | ❌ | v2.0 tinha SegmentedButton |
| Botão "Nova Câmera" (formulário modal) | ❌ | v2.0 tinha CameraFormModal |
| Editar câmera individual | ❌ | v2.0 tinha botão ✏ por linha |
| Deletar câmera | ❌ | v2.0 tinha botão 🗑 com confirmação |
| Botão "Monitor" por câmera | ❌ | v2.0 abria CameraMonitorModal |
| Copiar IP para clipboard | ❌ | v2.0 tinha botão 📋 |
| Ícone de marca por câmera | ❌ | v2.0 carregava assets/brands/{marca}.png |
| Exibir credenciais configuradas | ❌ | v2.0 mostrava ✓ ou ⚠ na coluna Auth |
| Exibir coluna de nome amigável | ❌ | v2.0 tinha coluna "Nome" |
| Reclassificar marcas | ✅ | OK |
| Auto-refresh a cada 10s | ❌ | v2.0 atualizava automaticamente |
| Atribuir grupo via dropdown | ✅ | OK |
| Atribuir localização via campo texto | ✅ | OK |
| Criar grupo pela tela de câmeras | ✅ | OK |

---

## 7. MÓDULO: GRUPOS

| Funcionalidade | Status | Observação |
|---|---|---|
| Listar grupos com total/online/offline | ✅ | OK |
| Criar novo grupo | ✅ | OK |
| Editar nome do grupo | ❌ | Não existe |
| Deletar grupo | ❌ | Não existe |
| Descrição do grupo | ❌ | v2.0 tinha campo de descrição |

---

## 8. MÓDULO: LOCALIZAÇÕES

| Funcionalidade | Status | Observação |
|---|---|---|
| View de localizações separada | ❌ | v2.0 tinha LocationsView completa |
| Criar localização com nome | ❌ | v2.0 tinha modal dedicado |
| Localização com latitude/longitude | ❌ | v2.0 armazenava coordenadas GPS |
| Descrição da localização | ❌ | v2.0 tinha campo |
| Deletar localização | ❌ | v2.0 tinha botão com confirmação |
| Ver câmeras por localização | ❌ | v2.0 exibia contador |

---

## 9. MÓDULO: MONITORAMENTO

| Funcionalidade | Status | Observação |
|---|---|---|
| Monitor contínuo (TCP ping) | ✅ | OK — intervalo 15s |
| Atualizar is_online + latency_ms | ✅ | OK |
| Modal de monitor por câmera | ❌ | v2.0 tinha CameraMonitorModal |
| Preview RTSP ao vivo (OpenCV) | ❌ | v2.0 capturava frames em tempo real |
| Diagnóstico completo (10 testes) | ❌ | v2.0 tinha DiagnosticRunner |
| Teste de ping e latência | ❌ | v2.0 media RTT e jitter |
| Teste de autenticação RTSP/HTTP | ❌ | v2.0 testava credenciais |
| Detecção de senha padrão | ❌ | v2.0 testava admin/admin etc. |
| Teste UPnP | ❌ | v2.0 detectava UPnP ativo |
| Teste certificado SSL | ❌ | v2.0 verificava expiração |
| Info ONVIF (modelo, firmware) | ❌ | v2.0 consultava ONVIF GetDeviceInfo |
| Análise de stream (FPS, codec, freeze) | ❌ | v2.0 analisava qualidade do stream |
| Snapshot HTTP | ❌ | v2.0 tentava capturar imagem via HTTP |
| Conflito de IP | ❌ | v2.0 detectava duplicidade ARP |

---

## 10. MÓDULO: ADMINISTRAÇÃO

| Funcionalidade | Status | Observação |
|---|---|---|
| View de administração | ❌ | v2.0 tinha AdminView completa |
| CRUD de usuários | ❌ | Criar, editar, ativar/desativar |
| Tabela de permissões por papel | ❌ | v2.0 exibia matriz visual |
| Papel OPERATOR | ❌ | Intermediário entre ADMIN e VIEWER |

---

## 11. MÓDULO: CÂMERA — FORMULÁRIO

| Funcionalidade | Status | Observação |
|---|---|---|
| Modal de criação de câmera | ❌ | v2.0 tinha CameraFormModal |
| Campo nome amigável | ❌ | v2.0 permitia nomear câmera |
| Campo usuário/senha da câmera | ❌ | v2.0 armazenava credenciais |
| Dropdown de localização | ❌ | v2.0 listava locations |
| Dropdown de grupo | ❌ | v2.0 listava groups |
| Botão "Testar Conexão" | ❌ | v2.0 testava RTSP/HTTP na hora |
| Editar câmera existente | ❌ | v2.0 abria modal preenchido |

---

## 12. PROBLEMAS IDENTIFICADOS NA VERSÃO ATUAL

### 12.1 Botões que não funcionam / comportamento incorreto

| Botão/Ação | Problema |
|---|---|
| Botão "Salvar no banco" (câmeras) | Funciona mas não confirma visualmente se a câmera já existe |
| Botão "Reclassificar agora" | Funciona mas não tem feedback imediato de progresso |
| Navegação entre abas | Às vezes a aba de câmeras não atualiza ao trocar |
| Scan — botão "Parar" | Para o scan mas não reseta o label de progresso corretamente |
| Monitor de câmeras | Atualiza status mas não reflete na UI sem trocar de aba |

### 12.2 Limitações de dados

| Problema | Impacto |
|---|---|
| Câmera não tem campo de credenciais | Impossível testar autenticação |
| Câmera não tem campo de nome amigável | Todas ficam como "Câmera X.X.X.X" |
| Localização é campo de texto livre | Sem estrutura (sem GPS, sem CRUD) |
| Sem coluna "nome" na lista | Difícil identificar câmeras |
| Sem porta ONVIF no modelo | Não pode usar ONVIF após salvar |

### 12.3 Deprecation Warnings (não críticos, mas devem ser corrigidos)
- `datetime.utcnow()` → usar `datetime.now(datetime.UTC)`
- `ft.border.all()` → usar `ft.Border.all()`
- `ft.padding.all()` → usar `ft.Padding.all()`

---

## 13. PRIORIDADES DE IMPLEMENTAÇÃO

### P0 — Crítico (app não serve sem isso)
1. **Botões de ação por câmera**: Editar, Deletar, Monitor
2. **Formulário de câmera**: Modal com nome, credenciais, grupo, localização
3. **Deletar câmera** com confirmação
4. **Feedback visual no scanner**: estado do botão, contadores, empty states

### P1 — Alta prioridade (melhora usabilidade muito)
5. **Painel de monitor por câmera**: status + diagnóstico básico
6. **Coluna "Nome"** na lista de câmeras
7. **Credenciais por câmera** (username/password no model)
8. **Filtro Todas/Online/Offline** na lista
9. **Botão de refresh** nas views
10. **Toast notifications** de feedback

### P2 — Médio (completa o produto)
11. **Administração de usuários** (CRUD + roles)
12. **View de Localizações** (CRUD)
13. **Papel OPERATOR** intermediário
14. **Indicador "Já adicionada"** no card do scanner
15. **Validação de CIDR grande** no scanner

### P3 — Melhorias (paridade com v2.0)
16. **Preview RTSP** com OpenCV
17. **Diagnóstico completo** (10 testes)
18. **Resolução de nome via HTTP banner + ONVIF**
19. **Dashboard completo** (4 cards, proporção, ações rápidas, recentes)
20. **Localização com GPS** (latitude/longitude)

---

## 14. MODELOS DE DADOS — MELHORIAS NECESSÁRIAS

### Camera (adicionar campos)
```python
name          = CharField(default="")        # P1 — nome amigável
username      = CharField(null=True)         # P1 — credencial de acesso
password      = CharField(null=True)         # P1 — credencial de acesso
port_rtsp     = IntegerField(default=554)    # P1 — porta RTSP
port_http     = IntegerField(default=80)     # P1 — porta HTTP
port_onvif    = IntegerField(default=8080)   # P2 — porta ONVIF
```

### Location (novo modelo)
```python
id          = AutoField()
name        = CharField(unique=True)
description = CharField(null=True)
latitude    = FloatField(null=True)
longitude   = FloatField(null=True)
```

### User (adicionar campo)
```python
full_name = CharField(null=True)    # P2 — nome completo
```

---

## 15. REFERÊNCIA RÁPIDA — COMO CADA TELA DEVE FUNCIONAR

### Login
1. Usuário digita login + senha → Enter ou clica "Entrar"
2. Credenciais inválidas → mensagem vermelha inline
3. Login OK → vai para Dashboard + inicia monitor

### Dashboard
1. Exibe 4 cards (total, online, offline, desconhecido)
2. Barra de proporção online vs offline
3. Ações rápidas (botões para navegar)
4. Lista das últimas 8 câmeras

### Scanner
1. CIDR preenchido automaticamente com a rede local
2. Clicar "Iniciar" → botão muda para "⏳ Escaneando..."
3. Progresso: "Escaneando 128/254 hosts..."
4. Contadores: "🌐 12 host(s)  📷 3 câmera(s)"
5. Cards aparecem em tempo real conforme encontradas
6. Cada card: marca, IP, MAC, portas, score, botão "Adicionar"
7. Se câmera já salva → botão "✓ Adicionada" desabilitado
8. Ao terminar → toast "Scan concluído — X câmera(s)"
9. Estados vazios contextuais

### Lista de Câmeras
1. Tabela com: status, marca, nome, IP, latência, local, grupo, auth, ações
2. Busca filtra em tempo real
3. Filtro: Todas / Online / Offline
4. Botões por linha: 👁 Monitor | ✏ Editar | 🗑 Deletar
5. "Nova Câmera" abre formulário modal
6. Auto-refresh a cada 10s

### Modal de Câmera
1. Campos: Nome, IP*, Usuário, Senha, Grupo, Localização
2. "Testar Conexão" → testa RTSP/HTTP na hora
3. Salvar → valida + salva + fecha

### Modal de Monitor
1. Painel esquerdo: preview RTSP ao vivo (se OpenCV)
2. Painel direito: botão "Executar Diagnóstico"
3. Diagnóstico roda 10 testes com barra de progresso
4. Resultado final: lista de problemas encontrados

### Grupos & Localizações
1. Duas listas lado a lado: Grupos | Localizações
2. Criar/editar/deletar cada um
3. Contador de câmeras em cada grupo/localização

### Administração (somente ADMIN)
1. Tabela de usuários com status, nome, role
2. Criar/editar/ativar/desativar usuários
3. Matriz de permissões por role (visual)

