// Regressão: variável usada sem estar definida (ReferenceError em tempo de execução).
// Em 28/11/2026 o gráfico de dias antigos quebrava com "ReferenceError: lastPrice is not defined"
// em IntradayCompassPanel.jsx e o build passava normalmente (o Vite não checa isso).
// O ESLint com `no-undef` pega esse erro antes do deploy.
import test from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ESLint } from 'eslint'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const eslint = new ESLint({ cwd: root })

const problems = (results) =>
  results.flatMap((r) =>
    r.messages
      .filter((m) => m.ruleId === 'no-undef' || m.fatal)
      .map((m) => `${path.relative(root, r.filePath)}:${m.line} ${m.message}`),
  )

test('o checador acha o bug original do lastPrice (fixture)', async () => {
  const code = `
export function Chart({ lastPt }) {
  const spotRef = Number(lastPrice || 0)
  return <div>{spotRef}{lastPt?.close}</div>
}
`
  const res = await eslint.lintText(code, { filePath: path.join(root, 'src/fixture-no-undef.jsx') })
  const found = problems(res)
  assert.equal(found.length, 1, `esperava 1 no-undef, veio: ${found.join(' | ')}`)
  assert.match(found[0], /'lastPrice' is not defined/)
})

test('a versão corrigida da fixture passa limpa', async () => {
  const code = `
export function Chart({ lastPt }) {
  const spotRef = Number(lastPt?.close || 0)
  return <div>{spotRef}</div>
}
`
  const res = await eslint.lintText(code, { filePath: path.join(root, 'src/fixture-ok.jsx') })
  assert.deepEqual(problems(res), [])
})

test('nenhum arquivo de src/ usa variável indefinida nem tem erro de sintaxe', { timeout: 280000 }, async () => {
  const res = await eslint.lintFiles(['src'])
  assert.deepEqual(problems(res), [], 'variável indefinida ou erro de sintaxe em src/')
})
