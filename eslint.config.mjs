// eslint.config.mjs (repo root)
import nextPlugin from '@next/eslint-plugin-next';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';
import n from 'eslint-plugin-n'; // Node/Nest용 (선택)
import eslint from '@eslint/js';
import globals from 'globals';
import eslintPluginPrettierRecommended from 'eslint-plugin-prettier/recommended';

const r = p => new URL(p, import.meta.url).pathname;
const __dirname = new URL('.', import.meta.url).pathname;

// Safely extract Next.js core-web-vitals rules for Flat Config
const nextCoreRules =
  nextPlugin?.configs?.['core-web-vitals']?.rules ?? nextPlugin?.configs?.recommended?.rules ?? {};

const commonTsRules = {
  'prettier/prettier': 'off',
  '@typescript-eslint/no-explicit-any': 'off',
  '@typescript-eslint/no-floating-promises': 'warn',
  '@typescript-eslint/no-unused-vars': [
    'warn',
    { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
  ],
  '@typescript-eslint/no-unsafe-argument': 'warn',
  '@typescript-eslint/no-unsafe-assignment': 'warn',
  '@typescript-eslint/no-unsafe-member-access': 'warn',
  '@typescript-eslint/no-unsafe-call': 'warn',
};

export default [
  eslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  ...tseslint.config(
    {
      // Monorepo / build outputs we don't want to lint
      ignores: ['eslint.config.mjs', 'dist/**', 'node_modules/**'],
    },
    {
      languageOptions: {
        globals: {
          ...globals.node,
          ...globals.jest,
        },
        // Use ESM since this config is .mjs
        sourceType: 'module',
        parserOptions: {
          // Enable TypeScript Project Service for type-aware linting (monorepo-friendly)
          projectService: true,
          // Also be explicit about the local tsconfig for better IDE integration
          project: ['./tsconfig.json'],
          tsconfigRootDir: __dirname,
        },
      },
    },
    {
      rules: {
        // House style
        ...commonTsRules,
      },
    },
  ),

  // 1) Nest/Node 영역 (예: apps/gateway, apps/workers)
  {
    files: ['apps/gateway/**/*.{ts,tsx,js,jsx}', 'apps/workers/**/*.{ts,js}'],
    languageOptions: {
      parserOptions: {
        project: [r('./apps/gateway/tsconfig.json'), r('./apps/workers/tsconfig.json')],
        tsconfigRootDir: r('.'),
      },
    },
    plugins: { n },
    // 필요시 type-aware 규칙 추가
    rules: {
      'n/no-unsupported-features/es-builtins': 'off', // Nest 런타임/트랜스파일 환경 고려
      // House style
      ...commonTsRules,
    },
  },

  // 2) Next 영역 (웹 앱만!)
  {
    files: ['apps/web/**/*.{ts,tsx,js,jsx}'],
    languageOptions: {
      parserOptions: {
        project: [r('./apps/web/tsconfig.json')],
        tsconfigRootDir: r('.'),
      },
    },
    plugins: { '@next/next': nextPlugin, 'react-hooks': reactHooks },
    rules: {
      ...nextCoreRules,
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },

  // 3) 공통 ignore
  {
    ignores: ['**/node_modules/**', '**/.next/**', '**/dist/**', '**/build/**'],
  },
  eslintPluginPrettierRecommended,
  {
    files: ['**/*.{ts,tsx,js,jsx}'],
    rules: {
      // Let Prettier handle formatting without ESLint warnings
      'prettier/prettier': 'off',
    },
  },
];
