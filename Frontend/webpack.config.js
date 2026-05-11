const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const CopyWebpackPlugin = require('copy-webpack-plugin');

module.exports = {
    // mode: 'production',
    mode: 'development',
    entry: {
        style: './js/style.js',
        main: './js/main.js'
    },
    output: {
        filename: '[name].js',
        path: path.join(__dirname, "/dist"),
        clean: true
    },
    optimization: {
        splitChunks: {
            chunks: 'all',
            cacheGroups: {
                vendor: {
                    name: 'vendor',
                    test: /three/,
                    chunks: 'all',
                }
            }
        },
        runtimeChunk: false
    },
    plugins: [
        new HtmlWebpackPlugin({
            template: './index.html',
            title: 'WechatJump'
        }),
        new CopyWebpackPlugin({
            patterns: [{
                from: './res',
                to: './res'
            }, {
                from: './js/lib',
                to: './js/lib'
            }]
        })
    ],
    devServer: {
        static: {
            directory: path.join(__dirname, "/dist")
        },
        client: {
            overlay: true
        },
        devMiddleware: {
            stats: 'errors-only'
        },
        hot: true,
        host: 'localhost',
        port: 6300,
        headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Credentials': true },
    },
    module: {
        rules: [
            {
                test: /\.js$/,
                exclude: /(node_modules|bower_components)/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: ['@babel/preset-env']
                    }
                }
            },
            {
                test: /\.less$/,
                use: [{
                    loader: "style-loader" // creates style nodes from JS strings
                }, {
                    loader: "css-loader" // translates CSS into CommonJS
                }, {
                    loader: "less-loader" // compiles Less to CSS
                }]
            },
            {
                test: /\.(eot|svg|ttf|woff|woff2|otf)$/,
                type: 'asset/resource'
            },
        ],
    },
};