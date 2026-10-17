<?php
declare(strict_types=1);

require_once __DIR__ . '/vendor/autoload.php';

use NFePHP\NFe\Make;

// Lê o JSON enviado pelo Python via pipe
$rawInput = file_get_contents('php://stdin');
$data = json_decode($rawInput, true);

if (!$data || !isset($data['tipo_operacao'])) {
    fwrite(STDERR, json_encode(['error' => 'Payload inválido ou tipo_operacao ausente']));
    exit(1);
}

try {
    $tipo = $data['tipo_operacao'];
    $nfe = new Make();

    $nfe->taginfNFe(['Id' => 'NFe' . date('YmdHis'), 'versao' => '4.00']);
    $nfe->tagide([
        'cUF' => 35,
        'cNF' => rand(10000000, 99999999),
        'natOp' => match ($tipo) {
            'VENDA' => 'Venda de mercadoria',
            'MOVIMENTACAO_ESTOQUE' => 'Ajuste de estoque',
            'ALTERACAO_PRECO' => 'Atualização de valor',
            default => 'Operação comercial'
        },
        'mod' => 65,
        'serie' => 1,
        'nNF' => rand(1, 99999),
        'dhEmi' => date('Y-m-d\TH:i:sP'),
        'tpNF' => 1,
        'idDest' => 1,
        'cMunFG' => 3550308,
        'tpImp' => 4,
        'tpEmis' => 1,
        'cDV' => 0,
        'tpAmb' => 2,
        'finNFe' => 1,
        'indFinal' => 1,
        'indPres' => 1,
        'procEmi' => 0,
        'verProc' => 'StockFlow_1.0'
    ]);

    $resultado = [
        'status' => 'AUTORIZADA',
        'chave_acesso' => '35' . date('ym') . '00000000000191' . '65' . '001' . sprintf('%09d', rand(1, 9999)) . '1' . rand(10000000, 99999999),
        'protocolo' => 'PRC-' . uniqid(),
        'tipo_operacao' => $tipo,
        'mensagem' => 'Nota fiscal emitida via CLI NFePHP com sucesso'
    ];

    echo json_encode($resultado);
    exit(0);

} catch (\Throwable $e) {
    fwrite(STDERR, json_encode(['error' => $e->getMessage()]));
    exit(1);
}
