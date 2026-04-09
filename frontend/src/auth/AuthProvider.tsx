import { createContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts';
import { setTokenProvider, setSilentRefreshProvider } from '@/api/client';
import { syncUser } from '@/api/auth';

const oidcConfig = {
  authority: import.meta.env.VITE_KEYCLOAK_URL ?? 'http://localhost:8080/realms/astro-service',
  client_id: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? 'astro-frontend',
  redirect_uri: `${window.location.origin}/auth/callback`,
  post_logout_redirect_uri: window.location.origin,
  scope: 'openid profile email',
  userStore: new WebStorageStateStore({ store: window.localStorage }),
};

export const userManager = new UserManager(oidcConfig);

export interface AuthContextValue {
  user: User | null;
  internalUserId: string | null;
  isLoading: boolean;
  login: () => void;
  loginWithCredentials: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

const INTERNAL_USER_ID_KEY = 'astro_internal_user_id';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [internalUserId, setInternalUserId] = useState<string | null>(
    () => localStorage.getItem(INTERNAL_USER_ID_KEY),
  );
  const [isLoading, setIsLoading] = useState(true);
  // Tracks whether a session is already active — used to skip sync on silent refresh
  const activeUserRef = useRef<User | null>(null);

  const handleSync = useCallback(async () => {
    try {
      const { id } = await syncUser();
      setInternalUserId(id);
      localStorage.setItem(INTERNAL_USER_ID_KEY, id);
    } catch (err) {
      console.error('[AuthProvider] sync failed:', err);
    }
  }, []);

  useEffect(() => {
    const getToken = async () => {
      const u = await userManager.getUser();
      if (!u || u.expired) {
        try {
          const refreshed = await userManager.signinSilent();
          return refreshed?.access_token ?? null;
        } catch {
          return null;
        }
      }
      return u.access_token;
    };

    setTokenProvider(getToken);

    setSilentRefreshProvider(async () => {
      try {
        const refreshed = await userManager.signinSilent();
        return refreshed?.access_token ?? null;
      } catch {
        return null;
      }
    });

    userManager.getUser().then(async (u) => {
      if (u && !u.expired) {
        activeUserRef.current = u;
        setUser(u);
        await handleSync();
      }
      setIsLoading(false);
    });

    const onUserLoaded = async (u: User) => {
      const isFreshLogin = !activeUserRef.current;
      activeUserRef.current = u;
      setUser(u);
      if (isFreshLogin) {
        await handleSync();
      }
    };
    const onUserUnloaded = () => {
      activeUserRef.current = null;
      setUser(null);
      setInternalUserId(null);
      localStorage.removeItem(INTERNAL_USER_ID_KEY);
    };

    userManager.events.addUserLoaded(onUserLoaded);
    userManager.events.addUserUnloaded(onUserUnloaded);
    return () => {
      userManager.events.removeUserLoaded(onUserLoaded);
      userManager.events.removeUserUnloaded(onUserUnloaded);
    };
  }, [handleSync]);

  const login = () => userManager.signinRedirect();

  const loginWithCredentials = useCallback(async (username: string, password: string) => {
    // ROPC flow — fires userLoaded event → onUserLoaded handles sync
    await userManager.signinResourceOwnerCredentials({ username, password });
  }, []);

  const logout = () => userManager.signoutRedirect();

  return (
    <AuthContext.Provider value={{ user, internalUserId, isLoading, login, loginWithCredentials, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
