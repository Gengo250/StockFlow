<?php
declare(strict_types=1);

require_once __DIR__ . '/vendor/autoload.php';

use NFePHP\NFe\Make;
use NFePHP\NFe\Tools;
use NFePHP\Common\Certificate;

header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Método não permitido']);
    exit;
}

$rawInput = file_get_contents('php://input');
$data = json_decode($rawInput, true);

if (!$data || !isset($data['tipo_operacao'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Payload inválido ou tipo_operacao ausente']);
    exit;
}

try {
    $tipo = $data['tipo_operacao']; // 'VENDA', 'MOVIMENTACAO_ESTOQUE', 'ALTERACAO_PRECO'

    // Mock/Simulação estruturada do NFePHP (preencha com dados do certificado A1 da empresa)
    $nfe = new Make();

    // 1. Tag infNFe / ide (Identificação da Nota)
    $nfe->taginfNFe([
        'Id' => 'NFe' . date('YmdHis'),
        'versao' => '4.00'
    ]);

    $nfe->tagide([
        'cUF' => 35, // SP
        'cNF' => rand(10000000, 99999999),
        'natOp' => match ($tipo) {
            'VENDA' => 'Venda de mercadoria',
            'MOVIMENTACAO_ESTOQUE' => 'Ajuste ou transferência de estoque',
            'ALTERACAO_PRECO' => 'Atualização de valor venal',
            default => 'Operação comercial'
        },
        'mod' => 65, // 65 = NFC-e, 55 = NF-e
        'serie' => 1,
        'nNF' => rand(1, 99999),
        'dhEmi' => date('Y-m-d\TH:i:sP'),
        'tpNF' => 1, // 1 = Saída
        'idDest' => 1,
        'cMunFG' => 3550308,
        'tpImp' => 4,
        'tpEmis' => 1,
        'cDV' => 0,
        'tpAmb' => 2, // 2 = Homologação / Testes
        'finNFe' => 1,
        'indFinal' => 1,
        'indPres' => 1,
        'procEmi' => 0,
        'verProc' => 'StockFlow_1.0'
    ]);

    // Resposta de sucesso estruturada
    $protocolo = 'PRC-' . uniqid();
    $chave = '35' . date('ym') . '00000000000191' . '65' . '001' . sprintf('%09d', rand(1, 9999)) . '1' . rand(10000000, 99999999);

    echo json_encode([
        'status' => 'AUTORIZADA',
        'chave_acesso' => $chave,
        'protocolo' => $protocolo,
        'tipo_operacao' => $tipo,
        'mensagem' => 'Nota fiscal emitida e processada com sucesso via NFePHP',
        'detalhes' => $data
    ]);
} catch (\Throwable $e) {
    http_response_code(500);
    echo json_encode([
        'status' => 'REJEITADA',
        'error' => $e->getMessage()
    ]);
}
