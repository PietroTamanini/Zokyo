---
name: Zokyo
description: Interface operacional multiempresa para assistências técnicas.
colors:
  dark-bg: "#0b0d10"
  dark-surface: "#15191f"
  light-bg: "#f5f6f8"
  light-surface: "#ffffff"
  primary-blue: "#2563eb"
  primary-blue-dark: "#1d4ed8"
  text-dark: "#f3f5f7"
  text-light: "#171a1f"
  success: "#2dd4bf"
  danger: "#ef4444"
  warning: "#f59e0b"
typography:
  body:
    fontFamily: 'Inter, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: 'Inter, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.8px"
rounded:
  sm: "6px"
  md: "8px"
  pill: "20px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "28px"
components:
  button-primary:
    backgroundColor: "{colors.primary-blue-dark}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "8px 18px"
  input:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.text-dark}"
    rounded: "{rounded.sm}"
    padding: "9px 13px"
---

# Design System: Zokyo

## Overview

**Creative North Star: "Central de operação confiável"**

O Zokyo é uma interface de operação, não uma página promocional. A prioridade visual é permitir que atendentes, técnicos, proprietários e administradores encontrem o próximo passo rapidamente, com baixa carga cognitiva e sinais de estado claros.

O sistema usa uma base escura como padrão, tema claro opcional, azul como ação primária e cores semânticas para sucesso, alerta e erro. A densidade é moderada: sidebar persistente em telas grandes, gaveta em telas pequenas, cartões e tabelas com separação suficiente para leitura operacional.

**Key Characteristics:**

- Operacional e escaneável.
- Azul reservado para ação e foco.
- Estados semânticos consistentes.
- Layout responsivo mobile-first.
- Profundidade por camadas, bordas e sombras discretas.

## Colors

O azul é a cor de ação; superfícies e texto mudam por tema, enquanto verde, vermelho e âmbar comunicam estados.

### Primary

- **Azul de ação** (`#2563eb`): foco, navegação ativa, links e ações primárias.
- **Azul profundo** (`#1d4ed8`): botões primários e estados de maior contraste.

### Neutral

- **Fundo escuro** (`#0b0d10`) e **fundo claro** (`#f5f6f8`): canvas principal.
- **Superfície escura** (`#15191f`) e **superfície clara** (`#ffffff`): sidebar, topbar, cards e formulários.
- **Texto escuro** (`#f3f5f7`) e **texto claro** (`#171a1f`): texto principal por tema.

### Semantic

- **Sucesso** (`#2dd4bf`): concluído, ativo e confirmação.
- **Erro** (`#ef4444`): falha, exclusão e risco.
- **Alerta** (`#f59e0b`): atenção, pendência e risco financeiro.

## Typography

**Body Font:** Inter, com fallback para Segoe UI, Roboto e Helvetica.

**Character:** compacta, funcional e legível em tabelas, formulários e dashboards.

### Hierarchy

- **Body** (400, 14px, 1.5): conteúdo operacional.
- **Label** (700, 11px, 1.2, espaçamento de 0.8px, uppercase): nomes de campos e grupos.
- **Navigation** (500, 14px): módulos e ações principais.
- **Data/technical** (JetBrains Mono quando aplicável): códigos, logs e valores técnicos.

## Layout

O shell usa sidebar fixa de 248px em desktop e drawer em mobile. O conteúdo principal usa `margin-left: 248px`, topbar sticky de 56px e padding de 28px. Grids de formulário usam gaps de 16px e colunas que colapsam abaixo de aproximadamente 820px.

Tabelas e listas devem preservar leitura horizontal sem causar overflow global. Em telas pequenas, formulários aumentam o tamanho dos campos para toque e a sidebar vira uma gaveta com overlay.

## Elevation & Depth

A profundidade é híbrida: bordas e diferenças de superfície fazem o trabalho principal; sombras são discretas e reservadas para sidebar, cards e estados de ação.

- Sombra padrão: `0 4px 24px rgba(0,0,0,0.5)` no tema escuro.
- Sombra pequena: `0 2px 10px rgba(0,0,0,0.4)` no tema escuro.
- Hover pode elevar botões primários em 1px, sem animações longas.

## Shapes

Controles usam raios pequenos e consistentes: 6px para inputs, 8px para botões/cards e 20px para pills, tags e alternadores. Bordas devem permanecer visíveis nos dois temas. Foco deve usar a borda azul e um ring de 3px.

## Components

### Buttons

- **Shape:** 8px; variantes pequenas usam 6px ou 5px.
- **Primary:** azul profundo, texto branco, padding `8px 18px`.
- **Hover / Focus:** escurecer levemente, elevar 1px e manter foco visível.
- **Ghost / Outline:** fundo transparente, borda e texto derivados do tema.

### Cards / Containers

- **Background:** superfície do tema.
- **Border:** `var(--border)` ou `var(--border2)`.
- **Internal Padding:** 16px ou 28px conforme densidade.
- **Shadow:** apenas quando o card precisa se separar do canvas.

### Inputs / Fields

- Fundo `var(--surface2)`, borda `var(--border2)`, raio 6px.
- Foco: borda azul e ring azul translúcido.
- Erro: borda vermelha e ring vermelho translúcido.

### Navigation

Sidebar fixa em desktop, drawer em mobile, item ativo com fundo azul translúcido e borda lateral azul. Grupos podem ser recolhidos e devem manter `aria-expanded` sincronizado.

## Do's and Don'ts

### Do:

- **Do** usar tokens do tema em vez de cores isoladas em novos componentes.
- **Do** manter estados de foco visíveis e mensagens de erro próximas ao campo.
- **Do** preservar o tenant atual em páginas, APIs e links públicos.
- **Do** testar claro, escuro, mobile e desktop antes de alterar o shell.

### Don't:

- **Don't** usar vermelho ou âmbar como decoração; são estados semânticos.
- **Don't** esconder ações importantes apenas em hover.
- **Don't** adicionar sombras fortes, gradientes decorativos ou animações longas em telas operacionais.
- **Don't** introduzir uma segunda landing para a mesma empresa; use aliases/domínios da configuração existente.
