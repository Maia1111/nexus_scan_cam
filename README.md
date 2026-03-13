# 🎥 Nexus Scan IP Cam

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-05998b.svg)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/Status-Ativo-success.svg)]()

**Nexus Scan** é uma solução profissional para monitoramento, inventário e análise de saúde de frotas de câmeras IP. Ele resolve o problema de falta de visibilidade sobre o estado das câmeras em redes complexas, permitindo que administradores saibam em tempo real quais dispositivos estão online, quais apresentam falhas e onde elas estão localizadas.

---

## 🎯 Por que usar o Nexus Scan?

Muitas vezes, administradores de rede só percebem que uma câmera parou de gravar quando precisam das imagens e elas não existem. O **Nexus Scan** elimina esse risco ao:

- 🔍 **Identificar Câmeras Automaticamente**: Varre a rede em busca de dispositivos de vídeo.
- 📊 **Gerar Relatórios Profissionais**: Relatórios em HTML e PDF organizados por setores/grupos.
- ⚡ **Monitorar Latência e Jitter**: Detecta instabilidades na rede antes que a imagem caia.
- 👤 **Controle de Acesso**: Sistema de login com permissões diferenciadas (Admin/User).

---

## 🚀 Principais Funcionalidades

- ✅ **Dashboard Moderno**: Visão macro de toda a sua rede de câmeras.
- 📁 **Organização por Setores**: Separe câmeras por grupos (ex: Portaria, Estoque, TI).
- 📑 **Relatórios Agrupados**: Gere PDFs detalhados que separam as câmeras por seus respectivos grupos.
- 🛡️ **Segurança**: Primeiro acesso automatizado para configuração do usuário administrador.
- 📱 **Interface Responsiva**: Acompanhe a saúde das câmeras pelo computador ou celular.

---

## 🛠️ Pré-requisitos

Antes de instalar, certifique-se de ter instalado em sua máquina:
- **Python 3.8 ou superior**
- **Pip** (Gerenciador de pacotes do Python)

### 📦 Dependências Principais
- `FastAPI`: Base do servidor web.
- `Peewee`: Gerenciamento do banco de dados SQLite.
- `WeasyPrint`: Motor de geração de PDFs profissionais.
- `Httpx`: Testes de latência e comunicação assíncrona.

---

## 🔧 Instalação

### 🪟 No Windows (Modo Fácil - Um Clique) 📸

Para facilitar o uso, criamos um automatizador que configura tudo e cria um ícone de câmera na sua Área de Trabalho.

1. **Baixe/Clone o projeto** e entre na pasta.
2. Clique com o botão direito no arquivo `install_shortcut.ps1` e selecione **"Executar com o PowerShell"**.
3. **Pronto!** Um ícone chamado **Nexus Scan** aparecerá na sua Área de Trabalho com a imagem de uma câmera.

A partir de agora, basta clicar nesse ícone de câmera para abrir o sistema! 🚀

---

### 🐧 No Linux (Ubuntu/Debian)

---

## 📖 Como Usar

1. **Primeiro Acesso**: Ao rodar o sistema pela primeira vez, você será direcionado para uma tela de **Setup**. Crie o seu usuário administrador.
2. **Cadastrar Câmeras**: Vá em "Scanner" para buscar câmeras na rede ou cadastre-as manualmente em "Câmeras".
3. **Organizar**: Crie Grupos (ex: "Setor 01") e associe suas câmeras a eles para manter tudo organizado.
4. **Relatórios**: Na página de **Grupos**, use os botões de PDF no topo para gerar um diagnóstico completo da saúde da sua rede.

---

## 🛡️ Licença

Este projeto é desenvolvido para fins profissionais de monitoramento. Verifique sempre as leis locais sobre privacidade e monitoramento de câmeras.

**Desenvolvido por Rogério Maia** 🚀🎥
