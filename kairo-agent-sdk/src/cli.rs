use reqwest;
use std::fs;
use std::path::Path;

pub async fn install_agent(
    github_url: &str,
    agents_dir: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("Fetching agent from {github_url}...");

    // Naive URL transform to raw github usercontent for demo
    let raw_url = github_url
        .replace("github.com", "raw.githubusercontent.com")
        .to_string()
        + "/main/manifest.toml";

    let resp = reqwest::get(&raw_url).await?.text().await?;
    let manifest: crate::AgentManifest = toml::from_str(&resp)?;

    let agent_dir = agents_dir.join(&manifest.agent.id);
    fs::create_dir_all(&agent_dir)?;

    fs::write(agent_dir.join("manifest.toml"), resp)?;

    println!(
        "Agent [{}] installed. Restart Kairo or it will hot-reload in <5 seconds.",
        manifest.agent.name
    );
    Ok(())
}
