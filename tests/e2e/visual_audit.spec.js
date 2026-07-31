const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;

test.skip(!email || !password, 'Defina E2E_EMAIL e E2E_PASSWORD para executar a auditoria autenticada.');

const pages = [
  ['dashboard', '/'],
  ['clientes', '/clientes'],
  ['os', '/os'],
  ['os-kanban', '/os/kanban'],
  ['os-nova', '/os/nova'],
  ['agenda', '/agenda'],
  ['coleta', '/coleta'],
  ['coleta-rota', '/coletas/rota'],
  ['estoque', '/estoque'],
  ['estoque-movimentacoes', '/estoque/movimentacoes'],
  ['compras-pecas', '/compras-pecas'],
  ['bancada', '/bancada'],
  ['checklists', '/checklists'],
  ['fornecedores', '/fornecedores'],
  ['financeiro', '/financeiro'],
  ['produtividade', '/produtividade'],
  ['laudos', '/laudos/'],
  ['laudo-novo', '/laudos/novo'],
  ['laudo-templates', '/laudos/templates'],
  ['relatorios', '/relatorios'],
  ['usuarios', '/usuarios'],
  ['logs', '/logs'],
  ['configuracoes', '/configuracoes'],
  ['notificacoes', '/configuracoes/notificacoes'],
  ['retencao', '/privacidade/retencao'],
  ['importacao', '/importacao/bancos'],
  ['seguranca', '/seguranca/2fa'],
  ['sessoes', '/seguranca/sessoes'],
  ['ajuda', '/ajuda'],
];

test.beforeEach(async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill(password);
  await Promise.all([
    page.waitForURL(url => !url.pathname.endsWith('/login')),
    page.getByRole('button', { name: 'Entrar' }).click(),
  ]);
});

for (const [name, path] of pages) {
  test(`${name} sem erros visuais ou de runtime`, async ({ page }, testInfo) => {
    const errors = [];
    page.on('console', message => {
      if (message.type() === 'error') errors.push(`console: ${message.text()}`);
    });
    page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
    page.on('response', response => {
      if (response.status() >= 500) errors.push(`http ${response.status()}: ${response.url()}`);
    });

    const response = await page.goto(path, { waitUntil: 'networkidle' });
    expect(response.status(), path).toBeLessThan(500);
    await expect(page.locator('body')).toBeVisible();

    const layout = await page.evaluate(() => {
      const root = document.documentElement;
      const overflowing = [...document.querySelectorAll('body *')]
        .filter(element => {
          const style = getComputedStyle(element);
          if (style.position === 'fixed' || style.display === 'none') return false;
          const rect = element.getBoundingClientRect();
          return rect.width > 0 && (rect.right > root.clientWidth + 2 || rect.left < -2);
        })
        .slice(0, 12)
        .map(element => `${element.tagName.toLowerCase()}.${[...element.classList].join('.')}`);
      return {
        horizontalOverflow: root.scrollWidth > root.clientWidth + 2,
        overflowing,
      };
    });
    // axe-core aplica estilos inline durante a instrumentacao; registre antes
    // para que a CSP estrita nao seja confundida com erro da aplicacao.
    const applicationErrors = [...errors];
    const accessibility = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const seriousViolations = accessibility.violations.filter(item => ['critical', 'serious'].includes(item.impact));

    await page.screenshot({
      path: testInfo.outputPath(`${name}.png`),
      fullPage: true,
    });
    expect(applicationErrors, `${path}\n${applicationErrors.join('\n')}`).toEqual([]);
    expect(layout.horizontalOverflow, `${path}: ${layout.overflowing.join(', ')}`).toBe(false);
    expect(
      seriousViolations.map(item => {
        const targets = item.nodes.map(node => node.target.join(' ')).join(', ');
        return `${item.id}: ${item.help} (${item.nodes.length}) [${targets}]`;
      }),
      `${path}: violacoes de acessibilidade`,
    ).toEqual([]);
  });
}

test('alternancia de tema persiste apos navegacao', async ({ page }) => {
  await page.goto('/');
  const before = await page.locator('html').getAttribute('data-theme');
  await page.getByRole('button', { name: 'Alternar tema' }).click();
  const expected = before === 'dark' ? 'light' : 'dark';
  await expect(page.locator('html')).toHaveAttribute('data-theme', expected);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', expected);
});

test('modal de cliente abre, valida e fecha sem recarregar', async ({ page }) => {
  await page.goto('/clientes');
  const newClient = page.getByRole('link', { name: /Cadastrar cliente/ });
  await newClient.click();
  await expect(page.locator('#modal .modal-title')).toHaveText('Cadastrar cliente');
  await expect(page.locator('#cliente-form [name="nome"]')).toBeFocused();
  await page.getByRole('button', { name: 'Salvar', exact: true }).click();
  await expect(page.locator('#cliente-form [name="nome"]')).toHaveClass(/input-error/);
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await expect(page.locator('#modal')).not.toHaveClass(/show/);
  await expect(newClient).toBeFocused();
});

test('indicador do dashboard navega para ordens', async ({ page }) => {
  await page.goto('/');
  await page.getByText('OS em aberto', { exact: true }).click();
  await expect(page).toHaveURL(/\/os\/?$/);
  await expect(page.locator('#content .page-title')).toHaveText('Ordens de serviço');
});

test('menu responsivo gerencia foco e estado acessivel', async ({ page }) => {
  await page.goto('/');
  const menu = page.locator('.hamburger');
  test.skip((page.viewportSize()?.width || 0) > 900, 'Gaveta desktop possui fluxo dedicado.');
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('button', { name: 'Fechar menu' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await expect(menu).toBeFocused();
});

test('gaveta desktop guarda e restaura o estado', async ({ page }) => {
  await page.goto('/');
  const closeDrawer = page.getByRole('button', { name: 'Guardar menu' });
  test.skip(!(await closeDrawer.isVisible()), 'Gaveta usa overlay neste viewport.');
  await closeDrawer.click();
  const openDrawer = page.getByRole('button', { name: 'Abrir menu' });
  await expect(openDrawer).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('body')).toHaveClass(/sidebar-collapsed/);
  await page.reload();
  await expect(page.locator('body')).toHaveClass(/sidebar-collapsed/);
  await openDrawer.click();
  await expect(page.locator('body')).not.toHaveClass(/sidebar-collapsed/);
});

test('modulos da navegacao expandem e recolhem links', async ({ page }) => {
  await page.goto('/');
  const mobileMenu = page.getByRole('button', { name: 'Abrir menu' });
  if ((page.viewportSize()?.width || 0) <= 900 && await mobileMenu.isVisible()) await mobileMenu.click();
  const principal = page.getByRole('button', { name: 'Atendimento' });
  const atendimentoLinks = page.locator('#nav-atendimento');
  const clientes = atendimentoLinks.getByRole('link', { name: 'Clientes', exact: true });
  const initiallyExpanded = await principal.getAttribute('aria-expanded') === 'true';
  if (initiallyExpanded) await principal.click();
  await expect(principal).toHaveAttribute('aria-expanded', 'false');
  await expect(clientes).toBeHidden();
  await principal.click();
  await expect(principal).toHaveAttribute('aria-expanded', 'true');
  await expect(clientes).toBeVisible();
});

test('navegacao rola dentro da gaveta com todos os modulos abertos', async ({ page }) => {
  const width = page.viewportSize()?.width || 1280;
  await page.setViewportSize({ width, height: 568 });
  await page.goto('/');

  const mobileMenu = page.getByRole('button', { name: 'Abrir menu' });
  if (await mobileMenu.isVisible()) await mobileMenu.click();

  const moduleButtons = page.locator('.nav-group-toggle');
  for (let index = 0; index < await moduleButtons.count(); index += 1) {
    const button = moduleButtons.nth(index);
    if (await button.getAttribute('aria-expanded') === 'false') await button.click();
  }

  const dimensions = await page.locator('#sidebar > nav').evaluate((nav) => ({
    clientHeight: nav.clientHeight,
    scrollHeight: nav.scrollHeight,
    overflowY: getComputedStyle(nav).overflowY,
  }));
  const sidebarBox = await page.locator('#sidebar').boundingBox();

  expect(dimensions.overflowY).toBe('auto');
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight);
  expect(sidebarBox.y).toBeGreaterThanOrEqual(0);
  expect(sidebarBox.y + sidebarBox.height).toBeLessThanOrEqual(569);

  const nav = page.locator('#sidebar > nav');
  await nav.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  await expect(moduleButtons.last()).toBeInViewport();
});
