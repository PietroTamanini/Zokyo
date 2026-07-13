const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const pages = [
  ['login', '/login', 200],
  ['recuperacao de senha', '/recuperar-senha', 200],
  ['convite invalido', '/convite/token-invalido', 410],
];

for (const [name, path, expectedStatus] of pages) {
  test(`${name} publica responsiva e acessivel`, async ({ page }, testInfo) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error' && !(expectedStatus >= 400 && message.text().includes(String(expectedStatus)))) {
        errors.push(message.text());
      }
    });

    const projectOctets = { compact: 10, mobile: 20, tablet: 30, desktop: 40, wide: 50 };
    const projectOctet = projectOctets[testInfo.project.name] || 60;
    const pageOctet = pages.findIndex(item => item[1] === path) + 1;
    const runOctet = Math.floor(Math.random() * 200) + 1;
    await page.context().setExtraHTTPHeaders({ 'X-Forwarded-For': `198.${projectOctet}.${pageOctet}.${runOctet}` });
    const response = await page.goto(path, { waitUntil: 'networkidle' });
    expect(response.status()).toBe(expectedStatus);
    await expect(page.locator('body')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2);
    expect(overflow, `${path}: overflow horizontal`).toBe(false);
    expect(errors, `${path}: erros de runtime`).toEqual([]);

    const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    const serious = accessibility.violations.filter(item => ['critical', 'serious'].includes(item.impact));
    expect(serious.map(item => item.id), `${path}: acessibilidade`).toEqual([]);
  });
}

test('login oferece navegacao por teclado e controle de senha', async ({ page }) => {
  await page.goto('/login');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Ir para o formulário de acesso' })).toBeFocused();
  await page.getByLabel('Senha').fill('segredo-visivel');
  const toggle = page.locator('#toggle-password');
  await toggle.click();
  await expect(page.getByLabel('Senha')).toHaveAttribute('type', 'text');
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await toggle.click();
  await expect(page.getByLabel('Senha')).toHaveAttribute('type', 'password');
});
