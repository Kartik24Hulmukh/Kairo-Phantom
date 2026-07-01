use std::path::Path;
use wasmtime::*;
use wasmtime_wasi::WasiCtxBuilder;

pub struct WasmSandbox {
    engine: Engine,
}

impl Default for WasmSandbox {
    fn default() -> Self {
        Self::new()
    }
}

impl WasmSandbox {
    pub fn new() -> Self {
        let engine = Engine::default();
        Self { engine }
    }

    pub fn execute_agent_wasm(
        &self,
        wasm_path: &Path,
        input_prompt: &str,
        document_context: &str,
    ) -> Result<String, Box<dyn std::error::Error>> {
        let mut linker = Linker::new(&self.engine);
        wasmtime_wasi::preview1::add_to_linker_sync(&mut linker, |s| s)?;

        let mut wasi_builder = WasiCtxBuilder::new();
        wasi_builder.env("PROMPT", input_prompt);
        wasi_builder.env("CONTEXT", document_context);
        let p1_ctx = wasi_builder.build_p1();

        let mut store = Store::new(&self.engine, p1_ctx);
        let module = Module::from_file(&self.engine, wasm_path)?;

        let instance = linker.instantiate(&mut store, &module)?;

        let run_func = instance.get_typed_func::<(), ()>(&mut store, "run")?;
        run_func.call(&mut store, ())?;

        // In a real WASI module, we'd capture stdout or have it write to a specific memory location/result
        // This is a stub returning a mocked WASM output.
        Ok(format!("[WASM Output for Prompt: {input_prompt}]"))
    }
}
