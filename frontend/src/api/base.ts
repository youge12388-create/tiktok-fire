const appBasePath = import.meta.env.BASE_URL.replace(/\/$/, '')

export const apiBaseUrl = `${appBasePath}/api/v1`

/** 为后端返回的站内相对地址补上 Vite 的部署前缀。 */
export function withAppBasePath(path: string): string {
  if (/^(?:[a-z][a-z\d+.-]*:)?\/\//i.test(path)) return path
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${appBasePath}${normalizedPath}`
}
