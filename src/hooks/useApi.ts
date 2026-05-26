import { useState, useEffect, useCallback } from 'react'

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  interval?: number
) {
  const [data, setData]       = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const fetch_ = useCallback(async () => {
    try {
      const result = await fetcher()
      setData(result)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error')
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    fetch_()
    if (interval) {
      const id = setInterval(fetch_, interval)
      return () => clearInterval(id)
    }
  }, [fetch_, interval])

  return { data, loading, error, refetch: fetch_ }
}

export function usePolling<T>(fetcher: () => Promise<T>, ms = 5000) {
  return useApi(fetcher, [], ms)
}
