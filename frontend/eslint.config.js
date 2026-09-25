import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  {
    files: ["src/**/*.{js,jsx}"],
    plugins: {
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...jsxA11y.configs.recommended.rules,
    },
    languageOptions: {
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
  },
];
