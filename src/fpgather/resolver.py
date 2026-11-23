"""Resolve manifests through a central dependency tree."""

from pathlib import Path

from .manifest import condition_matches, load_manifest, normalize_library_name
from .model import Source, SourcesError


def resolve(
    entry: str | Path,
    *,
    project_root: str | Path,
    library: str = "work",
    libraries_root: str | Path = "target/dependency",
) -> list[Source]:
    """Resolve sources in dependency-first order.

    Entry and project paths are relative to the working directory.
    The libraries root is absolute or relative to the project root.
    Manifest paths follow the sources.yml rules independently.
    The entry library defaults to work. Dependencies keep their declared
    libraries.
    """
    dependency_root = (Path(project_root).resolve() / libraries_root).resolve()
    entry = Path(entry).resolve()
    library = normalize_library_name(library)
    stack = [("enter", entry, library, {})]
    active_chain = []
    active_paths = set()
    completed_contexts = set()
    manifest_cache = {}
    seen_sources = {}
    resolved_sources = []

    while stack:
        phase, path, current_library, payload = stack.pop()
        if phase == "exit":
            # Emit sources after all child manifests complete.
            context, sources = payload
            for source in sources:
                key = (source.library, source.path)
                previous = seen_sources.get(key)
                if previous is not None:
                    if previous.language_version != source.language_version:
                        raise SourcesError(
                            f"{path}: Conflicting language versions "
                            f"for {source.path}: "
                            f"{previous.language_version} "
                            f"and {source.language_version}"
                        )
                    continue
                seen_sources[key] = source
                resolved_sources.append(source)
            active_chain.pop()
            active_paths.remove(path)
            completed_contexts.add(context)
            continue

        if path in active_paths:
            raise SourcesError(
                "Cycle: " + " -> ".join(map(str, [*active_chain, path]))
            )
        if path not in manifest_cache:
            manifest_cache[path] = load_manifest(path)
        manifest = manifest_cache[path]
        defines = {**payload, **manifest["defines"]}
        definition_signature = tuple(
            sorted(
                (name, type(value).__name__, value)
                for name, value in defines.items()
            )
        )
        context = (path, current_library, definition_signature)
        if context in completed_contexts:
            continue

        sources = []
        for relative, options in manifest["sources"]:
            if "if" in options and not condition_matches(
                options["if"], defines
            ):
                continue
            source_path = (path.parent / relative).resolve()
            if not source_path.is_file():
                raise SourcesError(
                    f"{path}: Source file not found: {source_path}"
                )
            version = options.get(
                "language_version",
                manifest["language_defaults"].get(source_path.suffix.lower()),
            )
            if version is None:
                raise SourcesError(
                    f"{path}: No language version for {relative}"
                )
            sources.append(Source(source_path, current_library, version))

        children = []
        for child_library, relative, options in manifest["dependencies"]:
            if "if" in options and not condition_matches(
                options["if"], defines
            ):
                continue
            library_root = (dependency_root / child_library).resolve()
            child_manifest = (library_root / relative).resolve()
            if not child_manifest.is_relative_to(library_root):
                raise SourcesError(
                    f"{path}: Outside library directory: {relative}"
                )
            children.append(("enter", child_manifest, child_library, defines))
        active_chain.append(path)
        active_paths.add(path)
        stack.append(("exit", path, current_library, (context, sources)))
        # Push in reverse to visit children in their declared order.
        stack.extend(reversed(children))
    return resolved_sources
