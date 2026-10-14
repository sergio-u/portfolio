/**
 * Resolve hook: lets Node load the app's extensionless relative imports.
 *
 * Vite resolves `./foo` to `./foo.ts`; plain Node does not. Retrying with the
 * extension keeps the harness working without rewriting every import in the app.
 */
export async function resolve(specifier, context, next) {
  try {
    return await next(specifier, context)
  } catch (err) {
    if (!specifier.startsWith('.') || /\.[a-z]+$/i.test(specifier)) throw err
    return next(`${specifier}.ts`, context)
  }
}
