"""
Workflow Templates System

Allows defining reusable SQL analysis workflows that can be executed with parameters.

Example workflow YAML:
    name: "Monthly Payroll Summary"
    description: "Standard monthly payroll report by agency"
    parameters:
      - name: fiscal_year
        type: int
        required: true
      - name: agency_filter
        type: string
        required: false
        default: null
    
    steps:
      - type: query
        description: "Get total payroll by agency"
        sql_template: |
          SELECT 
            agency_name,
            SUM(CAST(REPLACE(regular_gross_paid, '$', '') AS REAL)) as total_payroll,
            COUNT(*) as employee_count
          FROM payroll
          WHERE fiscal_year = {{ fiscal_year }}
          {% if agency_filter %}
          AND agency_name LIKE '%{{ agency_filter }}%'
          {% endif %}
          GROUP BY agency_name
          ORDER BY total_payroll DESC
      
      - type: visualize
        chart_type: bar
        x_axis: agency_name
        y_axis: total_payroll
        title: "Payroll by Agency - {{ fiscal_year }}"
      
      - type: filter
        condition: "total_payroll > 1000000"
        description: "Filter to agencies with > $1M payroll"
"""

import os
import re
import yaml
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
from jinja2 import Template


@dataclass
class WorkflowParameter:
    """Parameter definition for a workflow"""
    name: str
    type: str
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass
class WorkflowStep:
    """A single step in a workflow"""
    step_type: str  # 'query', 'visualize', 'filter', 'analyze'
    description: str = ""
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Workflow:
    """A complete workflow definition"""
    name: str
    description: str
    parameters: List[WorkflowParameter]
    steps: List[WorkflowStep]
    category: str = "general"
    tags: List[str] = field(default_factory=list)


class WorkflowTemplateEngine:
    """
    Manages and executes workflow templates.
    """
    
    def __init__(self, workflows_dir: str = "app/workflows/templates"):
        self.workflows_dir = Path(workflows_dir)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self._workflows: Dict[str, Workflow] = {}
        self._load_workflows()
    
    def _load_workflows(self):
        """Load all workflow definitions from YAML files"""
        if not self.workflows_dir.exists():
            return
        
        for yaml_file in self.workflows_dir.glob("*.yml"):
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                
                workflow = self._parse_workflow(data)
                self._workflows[workflow.name] = workflow
                
            except Exception as e:
                print(f"Error loading workflow {yaml_file}: {e}")
    
    def _parse_workflow(self, data: Dict) -> Workflow:
        """Parse workflow from YAML data"""
        # Parse parameters
        parameters = []
        for param_data in data.get('parameters', []):
            parameters.append(WorkflowParameter(
                name=param_data['name'],
                type=param_data.get('type', 'string'),
                required=param_data.get('required', True),
                default=param_data.get('default'),
                description=param_data.get('description', '')
            ))
        
        # Parse steps
        steps = []
        for step_data in data.get('steps', []):
            steps.append(WorkflowStep(
                step_type=step_data['type'],
                description=step_data.get('description', ''),
                config={k: v for k, v in step_data.items() if k not in ['type', 'description']}
            ))
        
        return Workflow(
            name=data['name'],
            description=data.get('description', ''),
            parameters=parameters,
            steps=steps,
            category=data.get('category', 'general'),
            tags=data.get('tags', [])
        )
    
    def list_workflows(self, category: str = None) -> List[Dict[str, Any]]:
        """List available workflows"""
        workflows = []
        for name, workflow in self._workflows.items():
            if category and workflow.category != category:
                continue
            
            workflows.append({
                'name': workflow.name,
                'description': workflow.description,
                'category': workflow.category,
                'tags': workflow.tags,
                'parameters': [
                    {
                        'name': p.name,
                        'type': p.type,
                        'required': p.required,
                        'default': p.default,
                        'description': p.description
                    }
                    for p in workflow.parameters
                ]
            })
        
        return workflows
    
    def get_workflow(self, name: str) -> Optional[Workflow]:
        """Get a specific workflow by name"""
        return self._workflows.get(name)
    
    def validate_parameters(self, workflow: Workflow, params: Dict[str, Any]) -> tuple[bool, str]:
        """Validate parameters against workflow definition"""
        provided_params = set(params.keys())
        
        for param in workflow.parameters:
            if param.required and param.name not in provided_params:
                return False, f"Missing required parameter: {param.name}"
            
            if param.name in provided_params:
                value = params[param.name]
                # Type validation
                if param.type == 'int':
                    try:
                        int(value)
                    except ValueError:
                        return False, f"Parameter {param.name} must be an integer"
                elif param.type == 'float':
                    try:
                        float(value)
                    except ValueError:
                        return False, f"Parameter {param.name} must be a number"
        
        return True, ""
    
    def render_sql_template(self, sql_template: str, params: Dict[str, Any]) -> str:
        """Render SQL template with Jinja2"""
        template = Template(sql_template)
        return template.render(**params)
    
    async def execute_workflow(
        self,
        workflow_name: str,
        params: Dict[str, Any],
        db_adapter,
        user_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a workflow with given parameters.
        
        Returns:
            List of step results
        """
        workflow = self.get_workflow(workflow_name)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_name}' not found")
        
        # Validate parameters
        is_valid, error_msg = self.validate_parameters(workflow, params)
        if not is_valid:
            raise ValueError(f"Parameter validation failed: {error_msg}")
        
        # Fill in defaults
        for param in workflow.parameters:
            if param.name not in params and param.default is not None:
                params[param.name] = param.default
        
        results = []
        current_data = None
        
        for step in workflow.steps:
            step_result = {
                'step_type': step.step_type,
                'description': step.description,
                'success': True,
                'data': None,
                'error': None
            }
            
            try:
                if step.step_type == 'query':
                    # Execute SQL query
                    sql_template = step.config.get('sql_template', '')
                    sql = self.render_sql_template(sql_template, params)
                    
                    result = db_adapter.execute_query(sql)
                    current_data = result
                    step_result['data'] = result
                    step_result['sql'] = sql
                
                elif step.step_type == 'filter' and current_data:
                    # Filter the current data
                    condition = step.config.get('condition', '')
                    # Simple filtering - in production, use pandas or similar
                    # This is a simplified version
                    step_result['data'] = current_data
                
                elif step.step_type == 'visualize':
                    # Return visualization config
                    step_result['data'] = {
                        'chart_type': step.config.get('chart_type'),
                        'x_axis': step.config.get('x_axis'),
                        'y_axis': step.config.get('y_axis'),
                        'title': self.render_sql_template(step.config.get('title', ''), params)
                    }
                
                elif step.step_type == 'analyze':
                    # Analysis step - could call LLM for insights
                    step_result['data'] = {'message': 'Analysis step executed'}
                
            except Exception as e:
                step_result['success'] = False
                step_result['error'] = str(e)
            
            results.append(step_result)
        
        return results


# Global instance
workflow_engine = WorkflowTemplateEngine()
