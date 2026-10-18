'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';

export interface UsePollingOptions<T> {
  intervalMs?: number; // default: 8000ms (30000ms for notifications)
  enabled?: boolean; // default: true
  isEditing?: boolean; // if true, newly polled data will NOT overwrite state while editing
  onError?: (error: Error) => void;
  onSuccess?: (data: T) => void;
  initialData?: T | null;
}

export interface UsePollingResult<T> {
  data: T | null;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
  error: Error | null;
  isLoading: boolean;
  isRefreshing: boolean;
  lastUpdated: Date | null;
  secondsAgo: number;
  refresh: () => Promise<void>;
}

export function usePolling<T>(
  fetcher: (signal?: AbortSignal) => Promise<T>,
  options: UsePollingOptions<T> = {}
): UsePollingResult<T> {
  const {
    intervalMs = 8000,
    enabled = true,
    isEditing = false,
    onError,
    onSuccess,
    initialData = null,
  } = options;

  const [data, setData] = useState<T | null>(initialData);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(initialData === null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [secondsAgo, setSecondsAgo] = useState<number>(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const isEditingRef = useRef(isEditing);
  isEditingRef.current = isEditing;

  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  const abortControllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const errorCountRef = useRef<number>(0);
  const isMountedRef = useRef<boolean>(true);

  // Clear any existing poll timer
  const clearPollTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Core execution function
  const executeFetch = useCallback(async (isManualRefresh = false) => {
    if (!enabledRef.current || !isMountedRef.current) {
      return;
    }

    // Cancel in-flight request if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (isManualRefresh) {
      setIsRefreshing(true);
    }

    try {
      const result = await fetcherRef.current(controller.signal);
      if (!isMountedRef.current) return;

      errorCountRef.current = 0;
      setError(null);
      setLastUpdated(new Date());
      setSecondsAgo(0);

      // Never overwrite data if user is currently editing a form
      if (!isEditingRef.current) {
        setData(result);
      }
      onSuccessRef.current?.(result);
    } catch (err: any) {
      if (!isMountedRef.current || err.name === 'AbortError') return;

      errorCountRef.current += 1;
      const errorObj = err instanceof Error ? err : new Error(String(err));
      setError(errorObj);
      onErrorRef.current?.(errorObj);
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
        setIsRefreshing(false);
        scheduleNextPoll();
      }
    }
  }, []);

  // Schedule the next poll with exponential backoff on errors and pausing when hidden
  const scheduleNextPoll = useCallback(() => {
    clearPollTimer();
    if (!enabledRef.current || !isMountedRef.current) return;

    // Exponential backoff up to 60s
    let delay = intervalMs;
    if (errorCountRef.current > 0) {
      delay = Math.min(intervalMs * Math.pow(1.5, errorCountRef.current), 60000);
    }

    timerRef.current = setTimeout(() => {
      // Pause while document.hidden
      if (typeof document !== 'undefined' && document.hidden) {
        // Will resume when document becomes visible via visibilitychange listener
        return;
      }
      executeFetch();
    }, delay);
  }, [clearPollTimer, executeFetch, intervalMs]);

  // Window focus and visibility listener for instant refresh
  useEffect(() => {
    const handleVisibilityOrFocus = () => {
      if (typeof document !== 'undefined' && document.hidden) {
        return;
      }
      if (enabledRef.current && isMountedRef.current) {
        executeFetch();
      }
    };

    if (typeof window !== 'undefined') {
      window.addEventListener('focus', handleVisibilityOrFocus);
      document.addEventListener('visibilitychange', handleVisibilityOrFocus);
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleVisibilityOrFocus);
        document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
      }
    };
  }, [executeFetch]);

  // Seconds ago ticker (updates every 1s)
  useEffect(() => {
    const ticker = setInterval(() => {
      if (lastUpdated) {
        const diff = Math.floor((Date.now() - lastUpdated.getTime()) / 1000);
        setSecondsAgo(Math.max(0, diff));
      }
    }, 1000);

    return () => clearInterval(ticker);
  }, [lastUpdated]);

  // Mount/unmount lifecycle & immediate execution
  useEffect(() => {
    isMountedRef.current = true;
    if (enabled) {
      executeFetch();
    }

    return () => {
      isMountedRef.current = false;
      clearPollTimer();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [enabled, executeFetch, clearPollTimer]);

  const refresh = useCallback(async () => {
    await executeFetch(true);
  }, [executeFetch]);

  return {
    data,
    setData,
    error,
    isLoading,
    isRefreshing,
    lastUpdated,
    secondsAgo,
    refresh,
  };
}

export { LiveIndicator } from '@/components/ui/LiveIndicator';
export type { LiveIndicatorProps } from '@/components/ui/LiveIndicator';
