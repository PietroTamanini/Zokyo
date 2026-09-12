const { test, expect } = require('@playwright/test');

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;

test.skip(!email || !password, 'Defina E2E_EMAIL e E2E_PASSWORD para validar o admin global.');

async function login(page) {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill(password);
  await Promise.all([
    page.waitForURL(url => !url.pathname.endsWith('/login')),
    page.getByRole('button', { name: 'Entrar' }).click(),
  ]);
}

async function assertNoHorizontalOverflow(page) {
  const layout = await page.evaluate(() => {
    const root = document.documentElement;
    const overflowing = [...document.querySelectorAll('body *')]
      .filter(element => {
        const style = getComputedStyle(element);
        if (style.position === 'fixed' || style.display === 'none') return false;
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && (rect.right > root.clientWidth + 2 || rect.left < -2);
      })
      .slice(0, 10)
      .map(element => `${element.tagName.toLowerCase()}.${[...element.classList].join('.')}`);
    return { horizontalOverflow: root.scrollWidth > root.clientWidth + 2, overflowing };
  });
  expect(layout.horizontalOverflow, layout.overflowing.join(', ')).toBe(false);
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

for (const [name, url, heading] of [
  ['overview', '/platform', 'Visão geral'],
  ['organizations', '/platform?view=organizations', 'Empresas'],
  ['plans', '/platform?view=plans', 'Planos'],
  ['domains', '/platform?view=domains', 'Domínios'],
  ['new-company', '/platform?view=new-company', 'Nova empresa'],
]) {
  test(`${name} integrado na dashboard`, async ({ page }, testInfo) => {
    const errors = [];
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', error => errors.push(error.message));

    const response = await page.goto(url, { waitUntil: 'networkidle' });
    expect(response.status(), url).toBeLessThan(500);
    await expect(page.locator('body')).toHaveClass(/platform-workspace/);
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Navegação principal' }).getByText('Admin global')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Clientes' })).toHaveCount(0);
    await assertNoHorizontalOverflow(page);

    await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
    expect(errors).toEqual([]);
  });
}

test('menu responsivo do admin abre os modulos da plataforma', async ({ page }) => {
  test.skip((page.viewportSize()?.width || 0) > 900, 'Fluxo responsivo.');
  await page.goto('/platform?view=organizations', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Abrir menu' }).click();
  await expect(page.getByRole('button', { name: 'Fechar menu' })).toBeFocused();
  await expect(page.getByRole('link', { name: 'Empresas', exact: true })).toBeVisible();
  await assertNoHorizontalOverflow(page);
});
