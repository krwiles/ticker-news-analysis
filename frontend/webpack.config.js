const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");

module.exports = (_env, argv) => {
  const isProduction = argv.mode === "production";

  return {
    entry: "./src/index.tsx",
    output: {
      path: path.resolve(__dirname, "dist"),
      filename: isProduction ? "[name].[contenthash].js" : "[name].js",
      clean: true,
    },
    resolve: {
      extensions: [".tsx", ".ts", ".js"],
    },
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          exclude: /node_modules/,
          use: {
            loader: "ts-loader",
            // tsconfig.json sets noEmit for standalone `tsc --noEmit` type-checking;
            // webpack is the one actually emitting JS, so override it here.
            options: { compilerOptions: { noEmit: false } },
          },
        },
        // @tailwindcss/webpack is a loader (not a plugin) as of Tailwind v4 —
        // it compiles the `@import "tailwindcss"` in src/index.css.
        { test: /\.css$/, use: ["style-loader", "css-loader", "@tailwindcss/webpack"] },
      ],
    },
    plugins: [new HtmlWebpackPlugin({ template: "./public/index.html" })],
    devServer: {
      port: 3000,
      historyApiFallback: true,
      // The api container is what the skeleton page actually talks to.
      proxy: [{ context: ["/health"], target: "http://localhost:8000" }],
    },
    devtool: isProduction ? false : "eval-source-map",
  };
};
